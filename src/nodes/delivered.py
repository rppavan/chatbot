"""
Delivered menu nodes — returns, exchanges, and post-delivery issue reporting.
"""
import time
from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from src.state import ConversationState
from src.tools import oms_tools
from src.llm.intent import classify_intent


DELIVERED_OPTIONS = [
    "Return my order",
    "Exchange my order",
    "The order had an item missing",
    "Received wrong or damaged items",
    "Order shows delivered but not received",
    "Back to main menu",
]


def delivered_menu(state: ConversationState) -> dict:
    """Show delivered order action menu."""
    order_id = state.get("selected_order_id", "")

    menu_text = (
        f"✅ Order **{order_id}** has been delivered.\n\n"
        f"What would you like to do?\n\n"
        f"1️⃣ Return my order\n"
        f"2️⃣ Exchange my order\n"
        f"3️⃣ The order had an item missing\n"
        f"4️⃣ Received wrong or damaged items\n"
        f"5️⃣ Order shows delivered but not received\n"
        f"6️⃣ Back to main menu"
    )

    user_input = interrupt(menu_text)

    return {
        "messages": [AIMessage(content=menu_text)],
        "extracted_slots": {"dl_selection": user_input.strip()},
        "last_updated_at": time.time(),
    }


async def route_delivered(state: ConversationState) -> str:
    """Route delivered menu selection."""
    selection = state.get("extracted_slots", {}).get("dl_selection", "")

    direct_map = {
        "1": "delivered_return",
        "2": "delivered_exchange",
        "3": "delivered_missing",
        "4": "delivered_wrong",
        "5": "delivered_not_received",
        "6": "welcome",
    }
    if selection in direct_map:
        return direct_map[selection]

    intent = await classify_intent(selection, DELIVERED_OPTIONS)
    if "return" in intent.lower():
        return "delivered_return"
    if "exchange" in intent.lower():
        return "delivered_exchange"
    if "missing" in intent.lower():
        return "delivered_missing"
    if "wrong" in intent.lower() or "damaged" in intent.lower():
        return "delivered_wrong"
    if "not received" in intent.lower():
        return "delivered_not_received"
    if "main menu" in intent.lower() or "back" in intent.lower():
        return "welcome"

    return "delivered_return"


async def delivered_return(state: ConversationState) -> dict:
    """Check return options and initiate return."""
    order_id = state.get("selected_order_id", "")
    base_url = state.get("tenant_config", {}).get("api_base_url", "http://localhost:8100")

    # Check return eligibility
    try:
        options = await oms_tools.get_return_options(
            order_id, auth_token=state.get("auth_token"), base_url=base_url
        )
    except Exception as e:
        return {
            "messages": [AIMessage(content=f"❌ Unable to check return options: {str(e)}")],
            "last_updated_at": time.time(),
        }

    if not options.get("can_return"):
        return {
            "messages": [AIMessage(content=(
                f"❌ Order **{order_id}** is not eligible for return.\n"
                f"Return window is {options.get('return_window_days', 7)} days from delivery."
            ))],
            "return_options": options,
            "last_updated_at": time.time(),
        }

    # Show reasons and confirm
    reasons = options.get("reasons", [])
    reason_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(reasons))
    confirm_msg = (
        f"🔄 Return is available for order **{order_id}**.\n\n"
        f"Please select a reason for return:\n{reason_text}\n\n"
        f"Or type 'cancel' to go back."
    )
    user_input = interrupt(confirm_msg)

    if user_input.strip().lower() in ("cancel", "back", "no"):
        return {
            "messages": [AIMessage(content=confirm_msg), AIMessage(content="Return cancelled. Returning to menu.")],
            "last_updated_at": time.time(),
        }

    # Parse reason
    try:
        reason_idx = int(user_input.strip()) - 1
        reason = reasons[reason_idx] if 0 <= reason_idx < len(reasons) else reasons[0]
    except (ValueError, IndexError):
        reason = user_input.strip() if user_input.strip() else "Product not as expected"

    # Initiate return
    try:
        result = await oms_tools.initiate_return(
            order_id, reason=reason, auth_token=state.get("auth_token"), base_url=base_url
        )
        msg = (
            f"✅ Return initiated for order **{order_id}**!\n\n"
            f"📋 Return ID: {result.get('return_id', 'N/A')}\n"
            f"📅 Pickup scheduled: {result.get('pickup_date', 'TBD')[:10]}\n"
            f"💰 Refund of ₹{result.get('refund_amount', 0):.0f} will be processed "
            f"within {result.get('estimated_refund_days', 7)} business days after pickup."
        )
    except Exception as e:
        msg = f"❌ Failed to initiate return: {str(e)}"

    return {
        "messages": [AIMessage(content=confirm_msg), AIMessage(content=msg)],
        "return_options": options,
        "current_flow": "return",
        "last_updated_at": time.time(),
    }


async def delivered_exchange(state: ConversationState) -> dict:
    """Check exchange options and initiate exchange."""
    order_id = state.get("selected_order_id", "")
    base_url = state.get("tenant_config", {}).get("api_base_url", "http://localhost:8100")

    # Check exchange eligibility
    try:
        options = await oms_tools.get_exchange_options(
            order_id, auth_token=state.get("auth_token"), base_url=base_url
        )
    except Exception as e:
        return {
            "messages": [AIMessage(content=f"❌ Unable to check exchange options: {str(e)}")],
            "last_updated_at": time.time(),
        }

    if not options.get("can_exchange"):
        return {
            "messages": [AIMessage(content=(
                f"❌ Order **{order_id}** is not eligible for exchange.\n"
                f"Exchange window is {options.get('exchange_window_days', 7)} days from delivery."
            ))],
            "exchange_options": options,
            "last_updated_at": time.time(),
        }

    # Show available variants
    variants = options.get("available_variants", [])
    if not variants:
        return {
            "messages": [AIMessage(content="❌ No exchange variants available for this product.")],
            "last_updated_at": time.time(),
        }

    lines = [f"🔄 Exchange available for order **{order_id}**.\n\nAvailable options:\n"]
    for i, v in enumerate(variants, 1):
        diff = v.get("differential_amount", 0)
        diff_text = ""
        if diff > 0:
            diff_text = f" (+₹{diff:.0f})"
        elif diff < 0:
            diff_text = f" (-₹{abs(diff):.0f})"

        lines.append(
            f"{i}. {v.get('product_name', '')} — "
            f"Size: {v.get('size', 'N/A')}, Color: {v.get('color', 'N/A')}"
            f"{diff_text}"
        )

    lines.append("\nSelect a variant number, or type 'cancel' to go back:")
    variant_msg = "\n".join(lines)
    user_input = interrupt(variant_msg)

    if user_input.strip().lower() in ("cancel", "back", "no"):
        return {
            "messages": [AIMessage(content=variant_msg), AIMessage(content="Exchange cancelled.")],
            "last_updated_at": time.time(),
        }

    # Parse variant selection
    try:
        v_idx = int(user_input.strip()) - 1
        selected_variant = variants[v_idx] if 0 <= v_idx < len(variants) else variants[0]
    except (ValueError, IndexError):
        selected_variant = variants[0]

    diff_amount = selected_variant.get("differential_amount", 0)

    # If there's a differential, confirm
    if diff_amount > 0:
        diff_confirm = interrupt(
            f"⚠️ This exchange requires a differential payment of ₹{diff_amount:.0f}.\n"
            f"Do you want to proceed? (yes/no)"
        )
        if diff_confirm.strip().lower() not in ("yes", "y", "proceed"):
            return {
                "messages": [AIMessage(content="Exchange cancelled.")],
                "last_updated_at": time.time(),
            }

    # Initiate exchange
    try:
        result = await oms_tools.initiate_exchange(
            order_id,
            new_variant_id=selected_variant.get("variant_id", ""),
            auth_token=state.get("auth_token"),
            base_url=base_url,
        )
        msg = (
            f"✅ Exchange initiated for order **{order_id}**!\n\n"
            f"📋 Exchange ID: {result.get('exchange_id', 'N/A')}\n"
            f"📅 Pickup scheduled: {result.get('pickup_date', 'TBD')[:10]}\n"
        )
        if diff_amount > 0:
            msg += f"💳 Differential amount: ₹{diff_amount:.0f}\n"

        msg += "Our logistics partner will pick up the original item."

    except Exception as e:
        msg = f"❌ Failed to initiate exchange: {str(e)}"

    return {
        "messages": [AIMessage(content=variant_msg), AIMessage(content=msg)],
        "exchange_options": options,
        "exchange_differential_amount": diff_amount,
        "current_flow": "exchange",
        "last_updated_at": time.time(),
    }


def delivered_missing(state: ConversationState) -> dict:
    """Missing item — routes to agent handoff."""
    order_id = state.get("selected_order_id", "")
    msg = (
        f"😟 Sorry to hear that order **{order_id}** had a missing item.\n"
        f"This requires manual investigation.\n"
        f"I'll connect you with a support agent right away."
    )
    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }


def delivered_wrong(state: ConversationState) -> dict:
    """Wrong/damaged item — routes to agent handoff."""
    order_id = state.get("selected_order_id", "")
    msg = (
        f"😟 Sorry about the wrong/damaged items in order **{order_id}**.\n"
        f"This requires manual review.\n"
        f"I'll connect you with a support agent to resolve this."
    )
    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }


def delivered_not_received(state: ConversationState) -> dict:
    """Delivered but not received — routes to agent handoff."""
    order_id = state.get("selected_order_id", "")
    msg = (
        f"🔍 I understand order **{order_id}** shows as delivered but you haven't received it.\n"
        f"This needs to be investigated with the courier.\n"
        f"I'll connect you with a support agent for immediate assistance."
    )
    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }
