# Design Document: Multi-Tenant E-commerce CX Chatbot

## 1. System Overview

This document defines the technical design for implementing the Multi-Tenant CX Chatbot using **LangChain** (LLM orchestration, tool abstraction) and **LangGraph** (stateful guided flows as directed graphs). The system handles customer support across WhatsApp, Web Chat, and Social Media channels for multiple storefronts.

### 1.1 Design Principles

1. **Guided Flows First, LLM Second** -- Deterministic graph-driven flows handle structured journeys (order tracking, cancellation, returns). The LLM handles intent classification, slot extraction, FAQ generation, and fallback conversation.
2. **Shared Memory** -- A single `ConversationState` object is threaded through every node, tool call, and LLM invocation. This eliminates redundant API calls and keeps multi-step flows coherent.
3. **Tenant Isolation** -- Tenant context is resolved at ingress and attached to state. All downstream calls (APIs, LLM prompts, tool selection) are scoped to the tenant.
4. **Minimize Agent Handoffs** -- Automate as much as possible via API tools; escalate only on explicit failure paths.

---

## 2. High-Level Architecture

```
                                  +---------------------+
                                  |   Channel Adapters  |
                                  | (WhatsApp, Web, FB) |
                                  +--------+------------+
                                           |
                                           v
                                  +--------+------------+
                                  | Tenant Resolver     |
                                  | (channel_id -> tid) |
                                  +--------+------------+
                                           |
                                           v
                              +------------+-------------+
                              |  LangGraph StateGraph    |
                              |  (Guided Flow Engine)    |
                              |                          |
                              |  +---------+  +--------+ |
                              |  | Nodes   |  | Edges  | |
                              |  | (steps) |  | (cond) | |
                              |  +---------+  +--------+ |
                              |         |                 |
                              |         v                 |
                              |  +------+-------+        |
                              |  | Shared State |        |
                              |  | (memory)     |        |
                              |  +--------------+        |
                              +------|------|------------+
                                     |      |
                            +--------+      +--------+
                            v                        v
                   +--------+-------+      +---------+------+
                   |  LLM (Claude)  |      | LangChain Tools|
                   |  - Intent      |      | - Shopify      |
                   |  - Slot fill   |      | - OMS          |
                   |  - FAQ         |      | - Clickpost    |
                   |  - Fallback    |      | - Pragma       |
                   +----------------+      | - Freshdesk    |
                                           +----------------+
```

---

## 3. Shared State (ConversationState)

All nodes, tools, and LLM calls read from and write to a single typed state dictionary managed by LangGraph's `StateGraph`. This is the backbone of multi-step flow coherence.

### 3.1 State Schema

```python
from typing import TypedDict, Optional, Literal
from langgraph.graph import MessagesState

class ConversationState(MessagesState):
    """
    Extends MessagesState (which provides `messages: list[BaseMessage]`).
    All fields below are shared across every node, tool, and LLM call.
    """

    # --- Tenant Context (set once at ingress) ---
    tenant_id: str                          # e.g. "store-a"
    tenant_config: dict                     # store name, API keys, branding, Shopify domain
    channel: Literal["whatsapp", "web", "facebook", "instagram"]
    channel_identifier: str                 # WhatsApp number / widget domain / page ID

    # --- Session & Auth ---
    session_id: str
    is_authenticated: bool
    auth_token: Optional[str]
    user_id: Optional[str]
    user_phone: Optional[str]
    user_name: Optional[str]

    # --- OTP sub-flow ---
    otp_requested: bool
    otp_type: Optional[str]                 # "login" | "verify"

    # --- Order Context (set when user picks an order) ---
    orders: Optional[list[dict]]            # fetched order list (cached)
    selected_order_id: Optional[str]
    selected_order: Optional[dict]          # full order detail (cached)
    order_status: Optional[str]             # "pre_dispatch" | "shipped" | "out_for_delivery" |
                                            # "delivery_failed" | "delivered" | "cancelled" | "return_initiated"

    # --- Action Context ---
    current_flow: Optional[str]             # "cancel" | "return" | "exchange" | "track" |
                                            # "modify" | "faq" | "agent_handoff"
    cancel_options: Optional[dict]
    return_options: Optional[dict]
    exchange_options: Optional[dict]
    tracking_summary: Optional[dict]

    # --- Freshdesk ---
    freshdesk_ticket_id: Optional[str]

    # --- Navigation ---
    awaiting_input: Optional[str]           # what input the bot is waiting for
    csat_collected: bool

    # --- LLM scratch ---
    intent: Optional[str]                   # last classified intent
    extracted_slots: Optional[dict]         # LLM-extracted entities from free text
```

### 3.2 How State Flows Through the System

1. **Channel adapter** creates the initial state with `tenant_id`, `channel`, `session_id`.
2. Each **LangGraph node** receives the full state, performs its logic (API call, LLM call, or conditional routing), and returns a partial dict of updates.
3. LangGraph **merges** updates into the state automatically (reducer semantics).
4. **Tools** receive relevant state slices via tool input and return structured results that nodes write back to state.
5. **LLM calls** receive state-derived context in the system prompt (tenant branding, user name, order list) and return structured output parsed back into state.

### 3.3 State Persistence (Checkpointing)

```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver(conn_string=POSTGRES_URL)
graph = graph_builder.compile(checkpointer=checkpointer)

# Every invocation resumes from the last checkpoint for that thread_id
config = {"configurable": {"thread_id": f"{tenant_id}:{session_id}"}}
result = graph.invoke({"messages": [user_message]}, config=config)
```

- **thread_id** = `{tenant_id}:{session_id}` -- ensures tenant isolation at the persistence layer.
- On each `invoke`, LangGraph loads the latest checkpoint, applies the new input, runs the graph, and saves the new checkpoint.
- This provides natural conversation resumption across disconnects (WhatsApp sessions, page refreshes).

---

## 4. LangGraph Flow Design (Guided Flows)

The entire To-Be Flow is modeled as a single `StateGraph` with deterministic conditional edges. The LLM is called only in specific nodes (intent classification, slot extraction, FAQ answers, fallback).

### 4.1 Graph Topology

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(ConversationState)

# ── Entry ──
builder.add_node("resolve_tenant",     resolve_tenant)
builder.add_node("check_user",         check_user)
builder.add_node("guest_flow",         guest_flow)
builder.add_node("otp_send",           otp_send)
builder.add_node("otp_verify",         otp_verify)
builder.add_node("welcome",            welcome)

# ── Main Menu ──
builder.add_node("main_menu",          main_menu)
builder.add_node("classify_intent",    classify_intent)       # LLM node

# ── Order Flow ──
builder.add_node("fetch_orders",       fetch_orders)
builder.add_node("show_orders",        show_orders)
builder.add_node("select_order",       select_order)
builder.add_node("route_by_status",    route_by_status)       # conditional router

# ── Pre-Dispatch ──
builder.add_node("pre_dispatch_menu",  pre_dispatch_menu)
builder.add_node("cancel_order",       cancel_order)
builder.add_node("change_address",     change_address)
builder.add_node("change_phone",       change_phone)
builder.add_node("modify_product",     modify_product)

# ── Shipped / In-Transit ──
builder.add_node("shipped_menu",       shipped_menu)
builder.add_node("track_order",        track_order)
builder.add_node("cancel_shipped",     cancel_shipped)
builder.add_node("change_address_shipped", change_address_shipped)

# ── Out for Delivery / Failed ──
builder.add_node("ofd_track",          ofd_track)
builder.add_node("delivery_failed",    delivery_failed)

# ── Delivered ──
builder.add_node("delivered_menu",     delivered_menu)
builder.add_node("initiate_return",    initiate_return)
builder.add_node("initiate_exchange",  initiate_exchange)
builder.add_node("missing_item",       missing_item)
builder.add_node("wrong_damaged",      wrong_damaged)
builder.add_node("not_received",       not_received)

# ── Cancelled / Return-Initiated ──
builder.add_node("refund_check",       refund_check)
builder.add_node("track_return",       track_return)

# ── FAQ ──
builder.add_node("faq_categories",     faq_categories)
builder.add_node("faq_answer",         faq_answer)           # LLM node

# ── Shared Endpoints ──
builder.add_node("agent_handoff",      agent_handoff)
builder.add_node("csat_survey",        csat_survey)
builder.add_node("close_chat",         close_chat)

# ── Edges ──
builder.add_edge(START, "resolve_tenant")
builder.add_edge("resolve_tenant", "check_user")

builder.add_conditional_edges("check_user", route_auth, {
    "registered":    "welcome",
    "guest":         "guest_flow",
    "needs_otp":     "otp_send",
})

builder.add_edge("guest_flow",  "otp_send")
builder.add_edge("otp_send",    "otp_verify")
builder.add_edge("otp_verify",  "welcome")
builder.add_edge("welcome",     "main_menu")

builder.add_conditional_edges("main_menu", route_main_menu, {
    "orders":  "fetch_orders",
    "faqs":    "faq_categories",
})

builder.add_edge("fetch_orders", "show_orders")
builder.add_edge("show_orders",  "select_order")
builder.add_edge("select_order", "route_by_status")

builder.add_conditional_edges("route_by_status", route_order_status, {
    "pre_dispatch":      "pre_dispatch_menu",
    "shipped":           "shipped_menu",
    "out_for_delivery":  "ofd_track",
    "delivery_failed":   "delivery_failed",
    "delivered":         "delivered_menu",
    "cancelled":         "refund_check",
    "return_initiated":  "track_return",
})

# Pre-dispatch sub-edges
builder.add_conditional_edges("pre_dispatch_menu", route_pre_dispatch, {
    "cancel":         "cancel_order",
    "change_address": "change_address",
    "change_phone":   "change_phone",
    "modify_product": "modify_product",
})
builder.add_edge("modify_product", "agent_handoff")

# Shipped sub-edges
builder.add_conditional_edges("shipped_menu", route_shipped, {
    "track":          "track_order",
    "cancel":         "cancel_shipped",
    "change_address": "change_address_shipped",
})

# Delivered sub-edges
builder.add_conditional_edges("delivered_menu", route_delivered, {
    "return":       "initiate_return",
    "exchange":     "initiate_exchange",
    "missing":      "missing_item",
    "wrong":        "wrong_damaged",
    "not_received": "not_received",
})
builder.add_edge("missing_item",  "agent_handoff")
builder.add_edge("wrong_damaged", "agent_handoff")
builder.add_edge("not_received",  "agent_handoff")

# FAQ sub-edges
builder.add_conditional_edges("faq_categories", route_faq, {
    "delivery":      "faq_answer",
    "cancellation":  "faq_answer",
    "refunds":       "faq_answer",
    "account":       "faq_answer",
    "other":         "agent_handoff",
})

# All terminal actions -> CSAT -> close
for terminal in [
    "cancel_order", "track_order", "cancel_shipped",
    "change_address", "change_address_shipped", "change_phone",
    "ofd_track", "delivery_failed",
    "initiate_return", "initiate_exchange",
    "refund_check", "track_return",
    "faq_answer", "agent_handoff",
]:
    builder.add_edge(terminal, "csat_survey")

builder.add_edge("csat_survey", "close_chat")
builder.add_edge("close_chat", END)
```

### 4.2 Visual Mapping: To-Be Flow -> LangGraph Nodes

| To-Be Flow Node | LangGraph Node | Type |
|---|---|---|
| `CheckUser{Is Registered?}` | `check_user` | Conditional edge (route_auth) |
| `Welcome[Hi Name...]` | `welcome` | Deterministic node |
| `MenuHelpOrders` / `MenuFAQs` | `main_menu` | Conditional edge (route_main_menu) |
| `FetchOrders` | `fetch_orders` | Tool-calling node (OMS API) |
| `CheckStatus{Order Status}` | `route_by_status` | Conditional edge (route_order_status) |
| `PreDispatch` sub-tree | `pre_dispatch_menu` + children | Conditional edges |
| `Shipped` sub-tree | `shipped_menu` + children | Conditional edges |
| `Delivered` sub-tree | `delivered_menu` + children | Conditional edges |
| `AgentHandoff` | `agent_handoff` | Tool-calling node (Freshdesk API) |
| `EndNode[Close Chat & CSAT]` | `csat_survey` -> `close_chat` | Two-step terminal |

### 4.3 Interrupt Pattern (Human-in-the-Loop Input)

LangGraph nodes that need user input use `interrupt()` to pause the graph and wait for the next user message:

```python
from langgraph.types import interrupt, Command

def show_orders(state: ConversationState) -> dict:
    """Show order list and wait for user to pick one."""
    orders = state["orders"]
    menu = format_order_menu(orders)  # "1. Order #1234 - Shipped\n2. ..."

    # Pause graph, send menu to user, wait for reply
    selection = interrupt(menu)

    # User replied with their choice -- parse it
    selected_idx = parse_order_selection(selection, orders)
    selected = orders[selected_idx]

    return {
        "selected_order_id": selected["id"],
        "selected_order": selected,
        "order_status": normalize_status(selected["fulfillment_status"]),
    }
```

When the channel adapter receives the user's reply, it resumes the graph with:

```python
result = graph.invoke(Command(resume=user_reply), config=config)
```

This pattern applies to every node that presents a menu or asks a question: `main_menu`, `show_orders`, `pre_dispatch_menu`, `shipped_menu`, `delivered_menu`, `faq_categories`, `otp_verify`, `csat_survey`.

---

## 5. LangChain Tools (API Integrations)

Each external API is wrapped as a LangChain `StructuredTool`. Tools are invoked by graph nodes directly (not by the LLM agent), ensuring deterministic API orchestration per the API Flows diagram.

### 5.1 Tool Registry

```python
from langchain_core.tools import StructuredTool, InjectedToolArg
from typing import Annotated

# ── Auth Tools ──
otp_send_tool = StructuredTool.from_function(
    name="otp_send",
    description="Send OTP to user's phone number",
    func=api_otp_send,                      # POST /v1/otp/{type}
    args_schema=OTPSendInput,
)

otp_verify_tool = StructuredTool.from_function(
    name="otp_verify",
    description="Verify OTP entered by user",
    func=api_otp_verify,                    # POST /v1/otp/{type}/verify
    args_schema=OTPVerifyInput,
)

# ── User Tools ──
user_profile_tool = StructuredTool.from_function(
    name="get_user_profile",
    func=api_get_user_profile,              # GET /v2/user/{id}/profile
    args_schema=UserProfileInput,
)

user_address_tool = StructuredTool.from_function(
    name="get_user_addresses",
    func=api_get_user_addresses,            # GET /v2/user/{id}/address
    args_schema=UserAddressInput,
)

user_wallet_tool = StructuredTool.from_function(
    name="get_user_wallet",
    func=api_get_user_wallet,               # GET /v2/user/{id}/wallet
    args_schema=UserWalletInput,
)

# ── Order Tools ──
order_search_tool = StructuredTool.from_function(
    name="search_orders",
    func=api_order_search,                  # GET /v1/order-search
    args_schema=OrderSearchInput,
)

order_detail_tool = StructuredTool.from_function(
    name="get_order_detail",
    func=api_get_order,                     # GET /v1/order/{id}
    args_schema=OrderDetailInput,
)

tracking_tool = StructuredTool.from_function(
    name="get_tracking_summary",
    func=api_tracking_summary,              # GET /v1/order/{id}/tracking-summary
    args_schema=TrackingInput,
)

# ── Order Action Tools ──
cancel_options_tool = StructuredTool.from_function(
    name="get_cancel_options",
    func=api_cancel_options,                # GET /v1/order/{id}/cancel_options
    args_schema=OrderIdInput,
)

cancel_order_tool = StructuredTool.from_function(
    name="cancel_order",
    func=api_cancel_order,                  # POST /v1/order/{id}/cancel
    args_schema=CancelOrderInput,
)

return_options_tool = StructuredTool.from_function(
    name="get_return_options",
    func=api_return_options,                # GET /v1/order/{id}/return-options
    args_schema=OrderIdInput,
)

return_order_tool = StructuredTool.from_function(
    name="initiate_return",
    func=api_initiate_return,               # POST /v1/order/{id}/return
    args_schema=ReturnOrderInput,
)

exchange_options_tool = StructuredTool.from_function(
    name="get_exchange_options",
    func=api_exchange_options,              # GET /v1/order/{id}/exchange-options
    args_schema=OrderIdInput,
)

exchange_order_tool = StructuredTool.from_function(
    name="initiate_exchange",
    func=api_initiate_exchange,             # POST /v1/order/{id}/exchange
    args_schema=ExchangeOrderInput,
)

# ── Freshdesk Tools ──
create_ticket_tool = StructuredTool.from_function(
    name="create_freshdesk_ticket",
    func=api_create_freshdesk_ticket,
    args_schema=FreshdeskTicketInput,
)

# ── Logistics Tools ──
clickpost_track_tool = StructuredTool.from_function(
    name="clickpost_track",
    func=api_clickpost_track,               # AWB tracking, ETA
    args_schema=ClickpostTrackInput,
)

clickpost_cancel_tool = StructuredTool.from_function(
    name="clickpost_cancel",
    func=api_clickpost_cancel,              # Cancel shipped order
    args_schema=ClickpostCancelInput,
)

pragma_return_tool = StructuredTool.from_function(
    name="pragma_initiate_return",
    func=api_pragma_return,                 # Return logistics via Pragma
    args_schema=PragmaReturnInput,
)

pragma_exchange_tool = StructuredTool.from_function(
    name="pragma_initiate_exchange",
    func=api_pragma_exchange,               # Exchange logistics via Pragma
    args_schema=PragmaExchangeInput,
)
```

### 5.2 Tool Invocation Pattern (Node -> Tool, Not LLM -> Tool)

Tools are called directly by graph nodes, not via LLM tool-calling. This keeps the guided flows deterministic.

```python
def fetch_orders(state: ConversationState) -> dict:
    """Graph node: fetch orders using the search tool, write results to shared state."""
    result = order_search_tool.invoke({
        "phone": state["user_phone"],
        "tenant_id": state["tenant_id"],
        "auth_token": state["auth_token"],
    })
    return {"orders": result["orders"]}


def cancel_order(state: ConversationState) -> dict:
    """Graph node: execute cancellation, write result to state."""
    # Step 1: fetch cancel options
    options = cancel_options_tool.invoke({
        "order_id": state["selected_order_id"],
        "auth_token": state["auth_token"],
    })

    if not options["cancellable"]:
        return {
            "messages": [AIMessage(content="This order is no longer eligible for cancellation.")],
        }

    # Step 2: present reasons, wait for user choice
    reason = interrupt(format_cancel_reasons(options["reasons"]))

    # Step 3: execute cancel
    result = cancel_order_tool.invoke({
        "order_id": state["selected_order_id"],
        "reason": reason,
        "auth_token": state["auth_token"],
    })

    return {
        "messages": [AIMessage(content=f"Order #{state['selected_order_id']} has been cancelled. "
                                       f"Refund of {result['refund_amount']} will be processed in "
                                       f"{result['refund_timeline']}.")],
    }
```

### 5.3 API Flows Mapping to Tool Chains

Per the API_Flows.md diagram, multi-step API orchestrations map to node sequences:

| API Flow | Node(s) | Tools Called (in sequence) |
|---|---|---|
| Auth -> Verify -> Fetch Orders | `otp_send` -> `otp_verify` -> `fetch_orders` | `otp_send_tool` -> `otp_verify_tool` -> `order_search_tool` |
| Not Shipped -> Cancel | `cancel_order` | `cancel_options_tool` -> `cancel_order_tool` + Shopify refund |
| Not Shipped -> Cancel (Clickpost) | `cancel_shipped` | `clickpost_cancel_tool` |
| Delivered -> Return | `initiate_return` | `return_options_tool` -> `return_order_tool` -> `pragma_return_tool` |
| Delivered -> Exchange | `initiate_exchange` | `exchange_options_tool` -> `exchange_order_tool` -> `pragma_exchange_tool` |
| Return/Exchange -> Status | `track_return` | `order_detail_tool` (fetch per-item status, UTR, date) |

---

## 6. LLM Integration

The LLM is used surgically in specific nodes, not as a general-purpose agent.

### 6.1 LLM Roles

| Role | Node(s) | Purpose |
|---|---|---|
| **Intent Classification** | `classify_intent` | Classify free-text user input into a menu option when the user doesn't tap a button |
| **Slot Extraction** | `select_order` (fallback) | Extract order number from free text like "my blue shoes order" |
| **FAQ Generation** | `faq_answer` | Generate contextual answers from tenant-specific knowledge base |
| **Fallback / Chitchat** | `main_menu` (fallback) | Handle off-topic messages gracefully, redirect to menu |
| **CSAT Analysis** | `csat_survey` | Optionally classify free-text feedback sentiment |

### 6.2 Intent Classification Node

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)

INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an intent classifier for a customer support chatbot for {store_name}.
Classify the user's message into exactly one of these intents:
- orders: User wants help with an order (track, cancel, return, exchange, status)
- faqs: User has a general question (delivery policy, returns policy, account help)
- agent: User explicitly wants to talk to a human agent
- greeting: User is saying hello or starting a conversation
- unknown: Cannot determine intent

Respond with ONLY the intent label, nothing else."""),
    ("human", "{user_message}"),
])

intent_chain = INTENT_PROMPT | llm | StrOutputParser()

def classify_intent(state: ConversationState) -> dict:
    last_msg = state["messages"][-1].content
    intent = intent_chain.invoke({
        "store_name": state["tenant_config"]["store_name"],
        "user_message": last_msg,
    })
    return {"intent": intent.strip().lower()}
```

### 6.3 FAQ Answer Node (RAG)

```python
from langchain_core.prompts import ChatPromptTemplate

FAQ_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful support assistant for {store_name}.
Answer the customer's question using ONLY the provided context.
If the context doesn't contain the answer, say you'll connect them with an agent.
Keep answers concise (2-3 sentences max).

Context:
{faq_context}"""),
    ("human", "{question}"),
])

faq_chain = FAQ_PROMPT | llm | StrOutputParser()

def faq_answer(state: ConversationState) -> dict:
    question = state["messages"][-1].content
    # Retrieve relevant FAQ docs from tenant-specific vector store
    docs = faq_retriever.invoke(question, filter={"tenant_id": state["tenant_id"]})
    context = "\n".join([d.page_content for d in docs])

    answer = faq_chain.invoke({
        "store_name": state["tenant_config"]["store_name"],
        "faq_context": context,
        "question": question,
    })
    return {"messages": [AIMessage(content=answer)]}
```

---

## 7. Multi-Tenancy Design

### 7.1 Tenant Resolution

```python
# Tenant config store (database or config service)
TENANT_REGISTRY = {
    "whatsapp:+1234567890": "tenant-store-a",
    "web:storea.com":       "tenant-store-a",
    "whatsapp:+0987654321": "tenant-store-b",
    "fb:page-id-xyz":       "tenant-store-b",
}

def resolve_tenant(state: ConversationState) -> dict:
    key = f"{state['channel']}:{state['channel_identifier']}"
    tenant_id = TENANT_REGISTRY[key]
    tenant_config = load_tenant_config(tenant_id)  # API keys, store name, Shopify domain, branding
    return {
        "tenant_id": tenant_id,
        "tenant_config": tenant_config,
    }
```

### 7.2 Tenant-Scoped API Client

```python
class TenantAPIClient:
    """Wraps all API calls with tenant-specific base URL, auth headers, and Shopify credentials."""

    def __init__(self, tenant_config: dict):
        self.base_url = tenant_config["api_base_url"]
        self.shopify_domain = tenant_config["shopify_domain"]
        self.shopify_token = tenant_config["shopify_access_token"]
        self.freshdesk_domain = tenant_config["freshdesk_domain"]
        self.freshdesk_key = tenant_config["freshdesk_api_key"]
        self.clickpost_key = tenant_config["clickpost_api_key"]
        self.pragma_key = tenant_config["pragma_api_key"]

    async def order_search(self, phone: str, auth_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v1/order-search",
                params={"phone": phone},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            return resp.json()

    # ... similar methods for all endpoints
```

### 7.3 Data Isolation Guarantees

| Layer | Isolation Mechanism |
|---|---|
| **State persistence** | `thread_id` = `{tenant_id}:{session_id}` -- separate checkpoint namespaces |
| **API calls** | `TenantAPIClient` initialized per tenant with tenant-specific credentials |
| **FAQ/RAG** | Vector store filtered by `tenant_id` metadata on every retrieval |
| **LLM prompts** | Tenant `store_name` and branding injected; no cross-tenant data in context |
| **Freshdesk** | Separate Freshdesk domains/API keys per tenant |

---

## 8. Channel Adapter Layer

Each channel has a thin adapter that translates inbound messages to `ConversationState` updates and outbound `AIMessage`s to channel-native formats.

### 8.1 Adapter Interface

```python
from abc import ABC, abstractmethod

class ChannelAdapter(ABC):
    @abstractmethod
    async def parse_inbound(self, raw_event: dict) -> tuple[str, str, str]:
        """Returns (channel_identifier, session_id, user_message)."""
        ...

    @abstractmethod
    async def send_outbound(self, session_id: str, messages: list[AIMessage]) -> None:
        """Send bot responses in channel-native format (text, buttons, carousel)."""
        ...

    @abstractmethod
    def format_menu(self, options: list[str]) -> dict:
        """Format a list of options as channel-native interactive elements."""
        ...
```

### 8.2 Implementations

```python
class WhatsAppAdapter(ChannelAdapter):
    """WhatsApp Business API via webhook."""
    async def parse_inbound(self, raw_event: dict) -> tuple:
        phone = raw_event["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
        message = raw_event["entry"][0]["changes"][0]["value"]["messages"][0]
        text = message.get("text", {}).get("body", "")
        # For interactive replies (button/list), extract the selection
        if message["type"] == "interactive":
            text = message["interactive"]["button_reply"]["id"]
        return (phone, f"wa:{phone}", text)

    def format_menu(self, options: list[str]) -> dict:
        # WhatsApp interactive list message format
        return {
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": "Please select an option:"},
                "action": {
                    "button": "Options",
                    "sections": [{"rows": [
                        {"id": str(i), "title": opt} for i, opt in enumerate(options)
                    ]}],
                },
            },
        }

class WebChatAdapter(ChannelAdapter):
    """WebSocket-based web chat widget."""
    ...

class FacebookAdapter(ChannelAdapter):
    """Facebook Messenger webhook."""
    ...
```

### 8.3 Request Handler (Entrypoint)

```python
async def handle_message(channel: str, raw_event: dict):
    adapter = get_adapter(channel)
    channel_id, session_id, user_message = await adapter.parse_inbound(raw_event)

    # Resolve tenant from channel identifier
    tenant_id = TENANT_REGISTRY.get(f"{channel}:{channel_id}")
    config = {"configurable": {"thread_id": f"{tenant_id}:{session_id}"}}

    # Check if graph is mid-interrupt (waiting for user input) or starting fresh
    snapshot = graph.get_state(config)

    if snapshot.next:
        # Graph is paused at an interrupt -- resume with user's reply
        result = await graph.ainvoke(Command(resume=user_message), config=config)
    else:
        # New conversation turn -- invoke from START
        result = await graph.ainvoke({
            "messages": [HumanMessage(content=user_message)],
            "channel": channel,
            "channel_identifier": channel_id,
            "session_id": session_id,
        }, config=config)

    # Send bot responses back through channel
    new_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    await adapter.send_outbound(session_id, new_messages)
```

---

## 9. Agent Handoff (Freshdesk)

### 9.1 Handoff Node

```python
def agent_handoff(state: ConversationState) -> dict:
    """Create Freshdesk ticket and notify user."""
    client = TenantAPIClient(state["tenant_config"])

    # Build ticket context from shared state
    ticket_description = build_ticket_context(
        user_name=state.get("user_name"),
        user_phone=state.get("user_phone"),
        order_id=state.get("selected_order_id"),
        order_status=state.get("order_status"),
        current_flow=state.get("current_flow"),
        conversation_history=format_conversation(state["messages"][-10:]),  # last 10 messages
    )

    ticket = create_ticket_tool.invoke({
        "subject": f"Chatbot Escalation - {state.get('current_flow', 'General')}",
        "description": ticket_description,
        "email": state.get("user_email"),
        "phone": state.get("user_phone"),
        "priority": 2,  # Medium
        "tenant_config": state["tenant_config"],
    })

    return {
        "freshdesk_ticket_id": ticket["id"],
        "messages": [AIMessage(
            content=f"I've connected you with our support team. "
                    f"Your ticket ID is #{ticket['id']}. "
                    f"An agent will reach out to you shortly."
        )],
    }
```

### 9.2 Handoff Triggers (from To-Be Flow)

These nodes route directly to `agent_handoff`:
- `modify_product` -- product modifications in pre-dispatch
- `missing_item` -- missing items in delivered orders
- `wrong_damaged` -- wrong or damaged items
- `not_received` -- order shows delivered but not received
- `faq_categories` -> "Other Issues"

---

## 10. Conditional Edge Functions (Routers)

These functions inspect shared state and return the next node name.

```python
def route_auth(state: ConversationState) -> str:
    if state.get("is_authenticated"):
        return "registered"
    if state.get("user_phone"):
        return "needs_otp"
    return "guest"

def route_main_menu(state: ConversationState) -> str:
    intent = state.get("intent", "")
    if intent in ("orders", "greeting"):
        return "orders"
    if intent == "faqs":
        return "faqs"
    if intent == "agent":
        return "agent"       # direct to agent_handoff
    return "orders"          # default

def route_order_status(state: ConversationState) -> str:
    status = state.get("order_status", "")
    status_map = {
        "pre_dispatch":     "pre_dispatch",
        "preparing":        "pre_dispatch",
        "ready_to_dispatch":"pre_dispatch",
        "shipped":          "shipped",
        "in_transit":       "shipped",
        "out_for_delivery": "out_for_delivery",
        "delivery_failed":  "delivery_failed",
        "attempt_failed":   "delivery_failed",
        "delivered":        "delivered",
        "cancelled":        "cancelled",
        "return_initiated": "return_initiated",
        "return_in_progress":"return_initiated",
    }
    return status_map.get(status, "delivered")  # default to delivered

def route_pre_dispatch(state: ConversationState) -> str:
    return state.get("intent", "cancel")

def route_shipped(state: ConversationState) -> str:
    return state.get("intent", "track")

def route_delivered(state: ConversationState) -> str:
    return state.get("intent", "return")

def route_faq(state: ConversationState) -> str:
    category = state.get("intent", "other")
    if category == "other":
        return "other"       # -> agent_handoff
    return category          # -> faq_answer
```

---

## 11. Global Navigation (Back / Main Menu / Close)

Every interactive node must handle "go back" and "main menu" commands. This is implemented as a pre-processing wrapper.

```python
from langgraph.types import Command

GLOBAL_COMMANDS = {"main menu", "back", "start over", "close chat", "exit"}

def with_global_nav(node_fn):
    """Decorator: intercept global navigation commands before running node logic."""
    def wrapper(state: ConversationState):
        last_msg = state["messages"][-1].content.strip().lower()
        if last_msg in ("main menu", "start over", "back to main menu"):
            return Command(goto="main_menu")
        if last_msg in ("close chat", "exit", "bye"):
            return Command(goto="csat_survey")
        return node_fn(state)
    return wrapper

# Apply to all interactive nodes
main_menu        = with_global_nav(main_menu)
show_orders      = with_global_nav(show_orders)
pre_dispatch_menu = with_global_nav(pre_dispatch_menu)
shipped_menu     = with_global_nav(shipped_menu)
delivered_menu   = with_global_nav(delivered_menu)
faq_categories   = with_global_nav(faq_categories)
```

---

## 12. Project Structure

```
chatbot/
├── docs/                           # PRD, flows, this design doc
│   ├── Multi-Tenant_Chatbot_PRD.md
│   ├── To-Be_Flow.md
│   ├── API_Flows.md
│   └── Design_Document.md
├── src/
│   ├── main.py                     # FastAPI app, webhook endpoints
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py                # ConversationState TypedDict
│   │   ├── builder.py              # StateGraph construction (Section 4.1)
│   │   └── routers.py              # Conditional edge functions (Section 10)
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── auth.py                 # check_user, otp_send, otp_verify, guest_flow
│   │   ├── welcome.py              # welcome, main_menu
│   │   ├── orders.py               # fetch_orders, show_orders, select_order
│   │   ├── pre_dispatch.py         # pre_dispatch_menu, cancel_order, change_address, etc.
│   │   ├── shipped.py              # shipped_menu, track_order, cancel_shipped
│   │   ├── delivered.py            # delivered_menu, initiate_return, initiate_exchange
│   │   ├── returns.py              # refund_check, track_return
│   │   ├── faq.py                  # faq_categories, faq_answer (LLM)
│   │   ├── handoff.py              # agent_handoff
│   │   ├── navigation.py           # csat_survey, close_chat, global nav decorator
│   │   └── intent.py               # classify_intent (LLM)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── auth_tools.py           # OTP send/verify tools
│   │   ├── user_tools.py           # Profile, address, wallet tools
│   │   ├── order_tools.py          # Order search, detail, tracking tools
│   │   ├── action_tools.py         # Cancel, return, exchange tools
│   │   ├── freshdesk_tools.py      # Ticket creation tools
│   │   ├── clickpost_tools.py      # AWB tracking, cancel tools
│   │   └── pragma_tools.py         # Return/exchange logistics tools
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                 # ChannelAdapter ABC
│   │   ├── whatsapp.py             # WhatsApp Business API adapter
│   │   ├── webchat.py              # WebSocket web widget adapter
│   │   └── facebook.py             # Facebook Messenger adapter
│   ├── tenants/
│   │   ├── __init__.py
│   │   ├── resolver.py             # Tenant resolution from channel ID
│   │   ├── config.py               # Tenant config loader
│   │   └── client.py               # TenantAPIClient
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── prompts.py              # All prompt templates
│   │   └── chains.py               # Intent chain, FAQ chain
│   └── utils/
│       ├── formatters.py           # Message formatting helpers
│       └── validators.py           # Input validation
├── tests/
│   ├── test_graph.py               # Graph traversal tests
│   ├── test_nodes.py               # Individual node unit tests
│   ├── test_tools.py               # Tool invocation tests
│   └── test_adapters.py            # Channel adapter tests
├── alembic/                        # DB migrations (checkpoint store)
├── pyproject.toml
└── .env.example
```

---

## 13. Key Dependencies

| Package | Purpose |
|---|---|
| `langgraph >= 0.4` | StateGraph, conditional edges, interrupts, checkpointing |
| `langchain-core` | Tool abstraction, prompt templates, message types |
| `langchain-anthropic` | Claude LLM integration |
| `langchain-community` | Vector store retrievers for FAQ/RAG |
| `langgraph-checkpoint-postgres` | Persistent conversation state |
| `fastapi` | HTTP server for webhooks |
| `httpx` | Async HTTP client for API calls |
| `uvicorn` | ASGI server |
| `pydantic` | Input validation / tool schemas |
| `pgvector` / `chromadb` | Vector store for tenant FAQ embeddings |

---

## 14. Data Flow Summary

```
User Message
     │
     ▼
Channel Adapter (parse_inbound)
     │
     ▼
Tenant Resolver (channel_id -> tenant_config)
     │
     ▼
LangGraph.invoke / Command(resume=...)
     │
     ├──► State loaded from checkpoint (PostgresSaver)
     │
     ▼
Graph Node executes:
     │
     ├── Reads from ConversationState (shared memory)
     ├── Calls LangChain Tool (API) if needed
     ├── Calls LLM chain if needed
     ├── Calls interrupt() if user input needed
     └── Returns state updates (partial dict)
     │
     ▼
LangGraph merges updates into ConversationState
     │
     ├──► State saved to checkpoint
     │
     ▼
Conditional Edge evaluates next node
     │
     ▼
... (repeat until END or interrupt)
     │
     ▼
Channel Adapter (send_outbound)
     │
     ▼
User sees response
```
