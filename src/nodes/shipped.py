"""
Shipped menu nodes — tracking, cancellation, address change for shipped orders.
"""
import time
from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from src.state import ConversationState
from src.tools import oms_tools
from src.llm.intent import classify_intent


SHIPPED_OPTIONS = [
    "Where is my order?",
    "Cancel my order",
    "Change delivery address",
    "Back to main menu",
]


def shipped_menu(state: ConversationState) -> dict:
    """Show shipped/in-transit action menu."""
    order_id = state.get("selected_order_id", "")
    status = state.get("order_status", "shipped")
    status_label = status.replace("_", " ").title()

    menu_text = (
        f"🚚 Order **{order_id}** is currently **{status_label}**.\n\n"
        f"What would you like to do?\n\n"
        f"1️⃣ Where is my order?\n"
        f"2️⃣ Cancel my order\n"
        f"3️⃣ Change delivery address\n"
        f"4️⃣ Back to main menu"
    )

    user_input = interrupt(menu_text)

    return {
        "messages": [AIMessage(content=menu_text)],
        "extracted_slots": {"sh_selection": user_input.strip()},
        "last_updated_at": time.time(),
    }


async def route_shipped(state: ConversationState) -> str:
    """Route shipped menu selection."""
    selection = state.get("extracted_slots", {}).get("sh_selection", "")

    direct_map = {"1": "shipped_track", "2": "shipped_cancel", "3": "shipped_address", "4": "welcome"}
    if selection in direct_map:
        return direct_map[selection]

    intent = await classify_intent(selection, SHIPPED_OPTIONS)
    if "where" in intent.lower() or "track" in intent.lower():
        return "shipped_track"
    if "cancel" in intent.lower():
        return "shipped_cancel"
    if "address" in intent.lower():
        return "shipped_address"
    if "main menu" in intent.lower() or "back" in intent.lower():
        return "welcome"

    return "shipped_track"


async def shipped_track(state: ConversationState) -> dict:
    """Track a shipped order — display AWB, ETA, and tracking events."""
    order_id = state.get("selected_order_id", "")
    base_url = state.get("tenant_config", {}).get("api_base_url", "http://localhost:8100")

    try:
        tracking = await oms_tools.get_tracking_summary(
            order_id, auth_token=state.get("auth_token"), base_url=base_url
        )
    except Exception as e:
        return {
            "messages": [AIMessage(content=f"❌ Unable to fetch tracking info: {str(e)}")],
            "last_updated_at": time.time(),
        }

    lines = [f"📍 **Tracking for Order {order_id}**\n"]

    if tracking.get("awb"):
        lines.append(f"🏷 AWB: {tracking['awb']}")
    if tracking.get("courier"):
        lines.append(f"🚚 Courier: {tracking['courier']}")
    if tracking.get("eta"):
        lines.append(f"📅 Estimated Delivery: {tracking['eta'][:10]}")

    events = tracking.get("events", [])
    if events:
        lines.append("\n📋 **Tracking History:**")
        for event in events:
            lines.append(f"  • {event.get('status', '')} — {event.get('timestamp', '')[:16]}")

    msg = "\n".join(lines)

    return {
        "messages": [AIMessage(content=msg)],
        "tracking_summary": tracking,
        "last_updated_at": time.time(),
    }


async def shipped_cancel(state: ConversationState) -> dict:
    """Cancel a shipped order (in-transit cancellation / RTO)."""
    order_id = state.get("selected_order_id", "")
    base_url = state.get("tenant_config", {}).get("api_base_url", "http://localhost:8100")

    confirm_msg = (
        f"⚠️ Order **{order_id}** has already been shipped.\n"
        f"Cancelling it will initiate a Return to Origin (RTO) process.\n"
        f"The refund will be processed after the package returns to our warehouse.\n\n"
        f"Do you want to proceed? (yes/no)"
    )
    user_input = interrupt(confirm_msg)

    if user_input.strip().lower() not in ("yes", "y", "proceed"):
        return {
            "messages": [AIMessage(content=confirm_msg), AIMessage(content="Okay, no changes made.")],
            "last_updated_at": time.time(),
        }

    try:
        result = await oms_tools.cancel_order(
            order_id,
            reason="Customer requested cancellation (shipped)",
            auth_token=state.get("auth_token"),
            base_url=base_url,
        )
        msg = (
            f"✅ Cancellation initiated for order **{order_id}**.\n"
            f"📦 Return to Origin (RTO) process has been started.\n"
            f"💰 Refund of ₹{result.get('refund_amount', 0):.0f} will be processed after the package returns."
        )
    except Exception as e:
        msg = f"❌ Failed to cancel order: {str(e)}"

    return {
        "messages": [AIMessage(content=confirm_msg), AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }


def shipped_address(state: ConversationState) -> dict:
    """Change delivery address for a shipped order."""
    order_id = state.get("selected_order_id", "")
    msg = (
        f"📬 Delivery address changes for shipped orders require coordination with the courier.\n"
        f"I'll connect you with a support agent who can help with order **{order_id}**."
    )
    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }
