# Design Document: Multi-Tenant E-commerce CX Chatbot

## 1. System Overview

This document defines the technical design for implementing the Multi-Tenant CX Chatbot using **LangChain** (LLM orchestration, tool abstraction) and **LangGraph** (stateful guided flows as directed graphs). The system handles customer support across WhatsApp, Web Chat, and Social Media channels for multiple storefronts.

### 1.1 Design Principles

1. **Guided Flows First, LLM Second** -- Deterministic graph-driven flows handle structured journeys (order tracking, cancellation, returns). The LLM handles intent classification, slot extraction, FAQ generation, and fallback conversation.
2. **Shared Memory** -- A single `ConversationState` object is threaded through every node, tool call, and LLM invocation. This eliminates redundant API calls and keeps multi-step flows coherent.
3. **Tenant Isolation** -- `tenant_id` is provided in the request header by the platform. All downstream calls (APIs, LLM prompts, tool selection) are scoped to the tenant.
4. **Minimize Agent Handoffs** -- Automate as much as possible via API tools; escalate only on explicit failure paths.

---

## 2. High-Level Architecture

```
                                  +---------------------+
                                  |   Channel Adapters  |
                                  | (WhatsApp, Web, FB) |
                                  +--------+------------+
                                           |
                                           | tenant_id from
                                           | request header
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

All nodes, tools, and LLM calls read from and write to a single typed state dictionary managed by LangGraph's `StateGraph`.

### 3.1 State Schema

```python
from typing import TypedDict, Optional, Literal, Annotated
from langgraph.graph.message import add_messages
import time

class ConversationState(TypedDict):
    """
    All fields below are shared across every node, tool, and LLM call.
    Uses `add_messages` reducer to append chat history naturally.
    """
    messages: Annotated[list[BaseMessage], add_messages]

    # --- Tenant Context (from request header, set once at ingress) ---
    tenant_id: str                          # provided in request header, e.g. "store-a"
    tenant_config: dict                     # loaded from config store using tenant_id
    channel: Literal["whatsapp", "web", "facebook", "instagram"]
    channel_identifier: str                 # WhatsApp number / widget domain / page ID

    # --- Session & Auth ---
    session_id: str
    is_authenticated: bool
    auth_token: Optional[str]
    user_id: Optional[str]
    user_phone: Optional[str]
    user_name: Optional[str]
    
    # --- Guest Context ---
    guest_order_id: Optional[str]           # Used when a guest chooses to track via Order ID

    # --- OTP sub-flow ---
    otp_requested: bool
    otp_type: Optional[str]                 # "login" | "verify"

    # --- Order Context (set when user picks an order) ---
    orders: Optional[list[dict]]            # fetched order list (cached)
    selected_order_id: Optional[str]
    selected_order: Optional[dict]          # full order detail (cached)
    order_status: Optional[str]             # "pre_dispatch" | "shipped" | "out_for_delivery" |
                                            # "delivery_failed" | "delivered" | "cancelled" | "return_initiated"
    
    exchange_differential_amount: Optional[float] # Delta amount if exchanging for a different product variant

    # --- Action Context ---
    current_flow: Optional[str]             # "cancel" | "return" | "exchange" | "track" |
                                            # "modify" | "faq" | "agent_handoff"
    cancel_options: Optional[dict]
    return_options: Optional[dict]
    exchange_options: Optional[dict]
    tracking_summary: Optional[dict]

    # --- Freshdesk ---
    freshdesk_ticket_id: Optional[str]
    is_escalated: bool                      # If True, bypass LangGraph and route directly to Freshdesk agent

    # --- Navigation & System ---
    awaiting_input: Optional[str]           # what input the bot is waiting for
    csat_collected: bool
    last_updated_at: float                  # Timestamp used for cache invalidation

    # --- LLM scratch ---
    intent: Optional[str]                   # last classified intent
    extracted_slots: Optional[dict]         # LLM-extracted entities from free text
```

### 3.2 How State Flows Through the System

1. **Channel adapter** extracts `tenant_id` from the request header and creates the initial state.
2. Each **LangGraph node** receives the state, performs logic, and returns a dict of updates.
3. LangGraph **merges** updates into the state automatically (e.g., appending to `messages`).
4. **Tools** receive relevant state slices and return structured results.
5. **LLM calls** receive state-derived context and return parsed outputs.

### 3.3 State Persistence (Checkpointing)

```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver(conn_string=POSTGRES_URL)
graph = graph_builder.compile(checkpointer=checkpointer)

# Every invocation resumes from the last checkpoint for that thread_id
config = {"configurable": {"thread_id": f"{tenant_id}:{session_id}"}}
```
- **thread_id** = `{tenant_id}:{session_id}` -- ensures tenant isolation at the persistence layer.

---

## 4. LangGraph Flow Design (Guided Flows)

### 4.1 Visual Mapping: To-Be Flow -> LangGraph Nodes

| To-Be Flow Node | LangGraph Node | Type |
|---|---|---|
| `CheckUser{Is Registered?}` | `check_user` | Conditional edge (route_auth) |
| `GuestFlow[Prompt Phone/OrderID]` | `guest_flow` | Collects Order ID/Phone without forcing full OTP |
| `Welcome[Hi Name...]` | `welcome` | Deterministic node |
| `MenuHelpOrders` / `MenuFAQs` | `main_menu` | Conditional edge (route_main_menu) |
| `FetchOrders` | `fetch_orders` | Tool-calling node (OMS API) |
| `CheckStatus{Order Status}` | `route_by_status` | Conditional edge (route_order_status) |
| `PreDispatch` sub-tree | `pre_dispatch_menu` + children | Conditional edges |
| `Shipped` sub-tree | `shipped_menu` + children | Conditional edges |
| `Delivered` sub-tree | `delivered_menu` + children | Conditional edges |
| `AgentHandoff` | `agent_handoff` | Tool-calling node (Freshdesk API) |
| `EndNode[Close Chat & CSAT]` | `csat_survey` -> `close_chat` | Two-step terminal |

### 4.2 Interrupt Pattern (Human-in-the-Loop Input)

LangGraph nodes that need user input use `interrupt()` to pause the graph:

```python
from langgraph.types import interrupt, Command
import time

def show_orders(state: ConversationState) -> dict:
    """Show order list and wait for user to pick one."""
    orders = state["orders"]
    menu = format_order_menu(orders)

    # Pause graph, send menu to user, wait for reply
    selection = interrupt(menu)

    # User replied with their choice
    selected_idx = parse_order_selection(selection, orders)
    selected = orders[selected_idx]

    return {
        "selected_order_id": selected["id"],
        "selected_order": selected,
        "order_status": normalize_status(selected["fulfillment_status"]),
        "last_updated_at": time.time()
    }
```

---

## 5. LangChain Tools (API Integrations)

Tools are invoked by graph nodes directly (not by the LLM agent), ensuring deterministic API orchestration per the API Flows diagram.

### 5.1 Tool Invocation Pattern: Cancellation Branching

As defined in the `API_Flows.md`, cancellation logic branches depending on the system of record and shipping state.

```python
def cancel_order(state: ConversationState) -> dict:
    """Graph node: execute cancellation, write result to state."""
    order = state["selected_order"]
    auth_token = state["auth_token"]
    
    # Check if we need differential branching per API_Flows.md
    if order.get("origin") == "shopify":
        # Shopify direct cancel
        result = shopify_cancel_tool.invoke({"order_id": order["id"], "token": auth_token})
        refund_msg = "Refund initiated on Shopify."
    elif state["order_status"] == "shipped":
        # Clickpost cancel for in-transit
        result = clickpost_cancel_tool.invoke({"awb": order["awb"]})
        refund_msg = "Return to origin initiated via courier."
    else:
        # Standard OMS (UC Cancel)
        result = cancel_order_tool.invoke({"order_id": order["id"], "token": auth_token})
        refund_msg = f"Refund of {result['refund_amount']} will be processed."

    return {
        "messages": [AIMessage(content=f"Order cancelled successfully. {refund_msg}")],
        "last_updated_at": time.time()
    }
```

### 5.2 Tool Invocation Pattern: Exchange Differential Amounts

As defined in `API_Flows.md`, exchanges require checking for differential amounts before sending to Pragma.

```python
def initiate_exchange(state: ConversationState) -> dict:
    options = exchange_options_tool.invoke({"order_id": state["selected_order_id"]})
    
    # Pause graph to get user's exchange variant selection
    variant_selection = interrupt(format_exchange_options(options))
    
    # Calculate differential amount
    diff_amount = calculate_differential(state["selected_order"], variant_selection)
    
    if diff_amount > 0:
        # Pause again to confirm payment link
        payment_confirmation = interrupt(f"Exchange requires a differential payment of ${diff_amount}. Proceed to payment link?")
        if not payment_confirmation:
            return Command(goto="delivered_menu")
        # -> Trigger payment gateway tool here
    
    # Execute Exchange via Pragma
    result = pragma_exchange_tool.invoke({
        "order_id": state["selected_order_id"],
        "new_variant": variant_selection
    })
    
    return {
        "messages": [AIMessage(content="Exchange initiated. Our logistics partner will pick up the item.")],
        "exchange_differential_amount": diff_amount
    }
```

---

## 6. LLM Integration

### 6.1 Intent Classification Node
Classifies free-text user input into a menu option when the user doesn't tap a button.

### 6.2 FAQ Answer Node (RAG) with Fallback

```python
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import Command

def faq_answer(state: ConversationState) -> dict:
    question = state["messages"][-1].content
    docs = faq_retriever.invoke(question, filter={"tenant_id": state["tenant_id"]})
    
    # Fallback: If no docs found, escalate to human
    if not docs:
        return Command(goto="agent_handoff")
        
    context = "\n".join([d.page_content for d in docs])
    answer = faq_chain.invoke({
        "store_name": state["tenant_config"]["store_name"],
        "faq_context": context,
        "question": question,
    })
    
    # Fallback: If LLM is unsure based on context
    if "i don't know" in answer.lower() or "cannot answer" in answer.lower():
        return Command(goto="agent_handoff")
        
    return {"messages": [AIMessage(content=answer)]}
```

---

## 7. Multi-Tenancy Design

### 7.1 Tenant Context from Header
`tenant_id` is passed automatically in the request header by the platform. The channel adapter reads it directly and loads the config.

### 7.2 Tenant-Scoped API Client
Wraps all API calls with tenant-specific base URLs and auth headers.

### 7.3 Data Isolation Guarantees
- **State persistence**: `thread_id` = `{tenant_id}:{session_id}`
- **API calls**: `TenantAPIClient` initialized per tenant.
- **Freshdesk**: Separate Freshdesk domains/API keys per tenant.

### 7.4 FAQ Knowledge Base Ingestion
To populate the tenant-specific Vector DB:
- An asynchronous **Sync Job** runs daily (or triggered via webhook) connecting to the tenant's Freshdesk Knowledge Base or Shopify Pages.
- Documents are chunked, embedded, and stored in PGVector.
- **Crucial:** Every document is stored with metadata `{"tenant_id": "store-a"}` ensuring the `faq_retriever` strictly isolates knowledge during retrieval.

---

## 8. Channel Adapter & Request Handler

### 8.1 Adapter Interface
Translates inbound messages to `ConversationState` updates and outbound `AIMessage`s to channel-native formats.

### 8.2 Request Handler (Entrypoint & Cache TTL)

```python
import time

async def handle_message(channel: str, raw_event: dict, request: Request):
    adapter = get_adapter(channel)
    channel_id, session_id, user_message = await adapter.parse_inbound(raw_event)

    tenant_id = request.headers["X-Tenant-Id"]
    config = {"configurable": {"thread_id": f"{tenant_id}:{session_id}"}}
    snapshot = graph.get_state(config)
    
    # --- 1. Agent Handoff Bypass ---
    if snapshot.values and snapshot.values.get("is_escalated"):
        # The conversation is currently owned by a Freshdesk Agent. Bypass LangGraph.
        await route_to_freshdesk(snapshot.values["freshdesk_ticket_id"], user_message)
        return

    # --- 2. Cache Invalidation (TTL) ---
    if snapshot.values and snapshot.values.get("last_updated_at"):
        if (time.time() - snapshot.values["last_updated_at"]) > 3600: # 1 Hour TTL
            # Invalidate cached orders to force a re-fetch if user resumes old session
            snapshot.values["orders"] = None
            snapshot.values["selected_order"] = None

    # --- 3. Invoke Graph ---
    if snapshot.next:
        result = await graph.ainvoke(Command(resume=user_message), config=config)
    else:
        tenant_config = load_tenant_config(tenant_id)
        result = await graph.ainvoke({
            "messages": [HumanMessage(content=user_message)],
            "tenant_id": tenant_id,
            "tenant_config": tenant_config,
            "channel": channel,
            "channel_identifier": channel_id,
            "session_id": session_id,
            "last_updated_at": time.time()
        }, config=config)

    # Send responses
    new_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    await adapter.send_outbound(session_id, new_messages)
```

---

## 9. Agent Handoff (Freshdesk)

### 9.1 Handoff Node

```python
def agent_handoff(state: ConversationState) -> dict:
    """Create Freshdesk ticket, notify user, and lock state."""
    
    # ... Create ticket via create_ticket_tool ...
    
    return {
        "freshdesk_ticket_id": ticket["id"],
        "is_escalated": True,  # Locks the graph from processing further messages
        "messages": [AIMessage(
            content=f"I've connected you with our support team. "
                    f"Your ticket ID is #{ticket['id']}. "
                    f"An agent will reply to you here shortly."
        )],
    }
```

Once `is_escalated` is True, the webhook request handler routes all future user messages directly to Freshdesk as ticket replies. When the agent closes the ticket, a webhook from Freshdesk to the bot system should reset `is_escalated = False`.

---

## 10. Global Navigation & Project Structure

The project remains structured modularly (`src/graph`, `src/nodes`, `src/tools`, `src/adapters`) with a decorator pattern for global navigation commands like "Main Menu" or "Close Chat" seamlessly integrated around standard graph nodes.
