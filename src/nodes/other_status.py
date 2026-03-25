"""
Other status nodes — cancelled and return_initiated order statuses.
"""
import time
from langchain_core.messages import AIMessage

from src.state import ConversationState


def cancelled_status(state: ConversationState) -> dict:
    """Display refund status for a cancelled order."""
    order = state.get("selected_order", {})
    order_id = state.get("selected_order_id", "")

    refund_status = order.get("refund_status", "pending")
    refund_amount = order.get("refund_amount", order.get("total", 0))

    status_emoji = "✅" if refund_status == "processed" else "⏳"

    msg = (
        f"❌ Order **{order_id}** was cancelled.\n\n"
        f"{status_emoji} **Refund Status:** {refund_status.replace('_', ' ').title()}\n"
        f"💰 **Refund Amount:** ₹{refund_amount:.0f}\n"
    )

    if refund_status == "processed" and order.get("refund_date"):
        msg += f"📅 **Refund Date:** {order['refund_date'][:10]}\n"
    elif refund_status == "pending":
        msg += "📅 Refund will be processed within 5-7 business days.\n"

    msg += "\nIs there anything else I can help with?"

    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }


def return_initiated_status(state: ConversationState) -> dict:
    """Display return tracking and refund info for return-initiated orders."""
    order = state.get("selected_order", {})
    order_id = state.get("selected_order_id", "")

    return_status = order.get("return_status", "pending")
    refund_status = order.get("refund_status", "pending")
    pickup_date = order.get("return_pickup_date", "")

    msg = (
        f"🔄 Order **{order_id}** — Return in Progress\n\n"
        f"📦 **Return Status:** {return_status.replace('_', ' ').title()}\n"
    )

    if pickup_date:
        msg += f"📅 **Pickup Date:** {pickup_date[:10]}\n"

    msg += f"💰 **Refund Status:** {refund_status.replace('_', ' ').title()}\n"

    if refund_status == "pending":
        msg += "Refund will be processed within 7-10 business days after pickup.\n"

    msg += "\nIs there anything else I can help with?"

    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }
