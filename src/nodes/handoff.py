"""
Agent handoff node — stubbed for MVP (no Freshdesk integration).
"""
import time
import uuid
from langchain_core.messages import AIMessage

from src.state import ConversationState


def agent_handoff(state: ConversationState) -> dict:
    """
    Create a support ticket and mark conversation as escalated.
    Stubbed for MVP — generates a fake ticket ID.
    """
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    order_id = state.get("selected_order_id", "N/A")
    user_name = state.get("user_name", "Customer")

    msg = (
        f"🎫 I've created a support ticket for you.\n\n"
        f"📋 **Ticket ID:** #{ticket_id}\n"
        f"📦 **Order:** {order_id}\n"
        f"👤 **Name:** {user_name}\n\n"
        f"A support agent will review your request and get back to you shortly.\n"
        f"You can reference ticket **#{ticket_id}** for follow-ups."
    )

    return {
        "messages": [AIMessage(content=msg)],
        "freshdesk_ticket_id": ticket_id,
        "is_escalated": True,
        "last_updated_at": time.time(),
    }
