"""
ConversationState — shared state schema for the LangGraph chatbot.
All nodes, tools, and LLM calls read/write to this single typed dictionary.
"""
from typing import TypedDict, Optional, Literal, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class ConversationState(TypedDict):
    """
    Shared state threaded through every LangGraph node, tool call, and LLM invocation.
    Uses `add_messages` reducer to append chat history naturally.
    """
    # --- Chat history (appended via reducer) ---
    messages: Annotated[list[BaseMessage], add_messages]

    # --- Tenant Context (from request header, set once at ingress) ---
    tenant_id: str
    tenant_config: dict
    channel: Literal["whatsapp", "web", "facebook", "instagram"]
    channel_identifier: str

    # --- Session & Auth ---
    session_id: str
    is_authenticated: bool
    auth_token: Optional[str]
    user_id: Optional[str]
    user_phone: Optional[str]
    user_name: Optional[str]

    # --- Guest Context ---
    guest_order_id: Optional[str]

    # --- OTP sub-flow ---
    otp_requested: bool
    otp_type: Optional[str]

    # --- Order Context ---
    orders: Optional[list[dict]]
    selected_order_id: Optional[str]
    selected_order: Optional[dict]
    order_status: Optional[str]

    exchange_differential_amount: Optional[float]

    # --- Action Context ---
    current_flow: Optional[str]
    cancel_options: Optional[dict]
    return_options: Optional[dict]
    exchange_options: Optional[dict]
    tracking_summary: Optional[dict]

    # --- Freshdesk (stubbed) ---
    freshdesk_ticket_id: Optional[str]
    is_escalated: bool

    # --- Navigation & System ---
    awaiting_input: Optional[str]
    csat_collected: bool
    last_updated_at: float

    # --- LLM scratch ---
    intent: Optional[str]
    extracted_slots: Optional[dict]
