"""
Pre-dispatch menu nodes — cancel, modify, address/phone change for orders not yet shipped.
"""
import time
from langchain_core.messages import AIMessage
from langgraph.types import interrupt, Command

from src.state import ConversationState
from src.tools import oms_tools
from src.llm.intent import classify_intent


PRE_DISPATCH_OPTIONS = [
    "Cancel my order",
    "Change delivery address",
    "Change phone number",
    "Make changes in the product",
    "Back to main menu",
]


def pre_dispatch_menu(state: ConversationState) -> dict:
    """Show pre-dispatch action menu."""
    order_id = state.get("selected_order_id", "")
    menu_text = (
        f"📋 Order **{order_id}** is currently being prepared.\n\n"
        f"What would you like to do?\n\n"
        f"1️⃣ Cancel my order\n"
        f"2️⃣ Change delivery address\n"
        f"3️⃣ Change phone number\n"
        f"4️⃣ Make changes in the product\n"
        f"5️⃣ Back to main menu"
    )

    user_input = interrupt(menu_text)

    return {
        "messages": [AIMessage(content=menu_text)],
        "extracted_slots": {"pd_selection": user_input.strip()},
        "last_updated_at": time.time(),
    }


async def route_pre_dispatch(state: ConversationState) -> str:
    """Route pre-dispatch menu selection."""
    selection = state.get("extracted_slots", {}).get("pd_selection", "")

    direct_map = {
        "1": "pre_dispatch_cancel",
        "2": "pre_dispatch_address",
        "3": "pre_dispatch_phone",
        "4": "pre_dispatch_modify",
        "5": "welcome",
    }
    if selection in direct_map:
        return direct_map[selection]

    intent = await classify_intent(selection, PRE_DISPATCH_OPTIONS)
    if "cancel" in intent.lower():
        return "pre_dispatch_cancel"
    if "address" in intent.lower():
        return "pre_dispatch_address"
    if "phone" in intent.lower():
        return "pre_dispatch_phone"
    if "change" in intent.lower() or "product" in intent.lower() or "modify" in intent.lower():
        return "pre_dispatch_modify"
    if "main menu" in intent.lower() or "back" in intent.lower():
        return "welcome"

    return "pre_dispatch_cancel"


async def pre_dispatch_cancel(state: ConversationState) -> dict:
    """Cancel a pre-dispatch order."""
    order_id = state.get("selected_order_id", "")
    base_url = state.get("tenant_config", {}).get("api_base_url", "http://localhost:8100")

    # Get cancel options first
    try:
        options = await oms_tools.get_cancel_options(
            order_id, auth_token=state.get("auth_token"), base_url=base_url
        )
    except Exception:
        return {
            "messages": [AIMessage(content="❌ Unable to fetch cancellation options. Please try again later.")],
            "last_updated_at": time.time(),
        }

    if not options.get("can_cancel"):
        return {
            "messages": [AIMessage(content="❌ This order cannot be cancelled in its current status.")],
            "last_updated_at": time.time(),
        }

    # Ask for confirmation
    reasons = options.get("reasons", [])
    reason_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(reasons))
    confirm_msg = (
        f"Are you sure you want to cancel order **{order_id}**?\n\n"
        f"Please select a reason:\n{reason_text}\n\n"
        f"Or type 'no' to go back."
    )
    user_input = interrupt(confirm_msg)

    if user_input.strip().lower() in ("no", "back", "cancel"):
        return {
            "messages": [AIMessage(content=confirm_msg), AIMessage(content="Okay, cancellation aborted. Returning to menu.")],
            "last_updated_at": time.time(),
        }

    # Parse reason
    try:
        reason_idx = int(user_input.strip()) - 1
        reason = reasons[reason_idx] if 0 <= reason_idx < len(reasons) else reasons[0]
    except (ValueError, IndexError):
        reason = user_input.strip() if user_input.strip() else "Customer requested cancellation"

    # Execute cancellation
    try:
        result = await oms_tools.cancel_order(
            order_id, reason=reason, auth_token=state.get("auth_token"), base_url=base_url
        )
        msg = (
            f"✅ Order **{order_id}** has been cancelled successfully!\n\n"
            f"💰 Refund of ₹{result.get('refund_amount', 0):.0f} will be processed "
            f"via {result.get('refund_method', 'original payment method')} "
            f"within {result.get('estimated_refund_days', 5)} business days."
        )
    except Exception as e:
        msg = f"❌ Failed to cancel order: {str(e)}"

    return {
        "messages": [AIMessage(content=confirm_msg), AIMessage(content=msg)],
        "cancel_options": options,
        "last_updated_at": time.time(),
    }


def pre_dispatch_address(state: ConversationState) -> dict:
    """Change delivery address for a pre-dispatch order."""
    order_id = state.get("selected_order_id", "")
    msg = (
        f"📬 To change the delivery address for order **{order_id}**, "
        f"please contact our support team.\n\n"
        f"I'm creating a support request for you..."
    )
    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }


def pre_dispatch_phone(state: ConversationState) -> dict:
    """Change phone number for a pre-dispatch order."""
    order_id = state.get("selected_order_id", "")
    msg = (
        f"📱 To change the phone number for order **{order_id}**, "
        f"please contact our support team.\n\n"
        f"I'm creating a support request for you..."
    )
    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }


def pre_dispatch_modify(state: ConversationState) -> dict:
    """Request product modification — routes to agent handoff."""
    order_id = state.get("selected_order_id", "")
    msg = (
        f"🔧 Product modifications for order **{order_id}** require manual review.\n"
        f"I'll connect you with a support agent who can help."
    )
    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }
