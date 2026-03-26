"""
Order nodes — fetch orders, show order list, route by status.
"""
import time
from langchain_core.messages import AIMessage
from src.nodes import interrupt

from src.state import ConversationState
from src.tools import oms_tools


def _normalize_status(fulfillment_status: str) -> str:
    """Normalize order status to route categories."""
    status_map = {
        "pre_dispatch": "pre_dispatch",
        "preparing": "pre_dispatch",
        "ready_to_dispatch": "pre_dispatch",
        "shipped": "shipped",
        "in_transit": "shipped",
        "out_for_delivery": "out_for_delivery",
        "delivery_failed": "delivery_failed",
        "delivered": "delivered",
        "cancelled": "cancelled",
        "return_initiated": "return_initiated",
    }
    return status_map.get(fulfillment_status, "pre_dispatch")


async def fetch_orders(state: ConversationState) -> dict:
    """Fetch orders from OMS for the authenticated user."""
    base_url = state.get("tenant_config", {}).get("api_base_url", "http://localhost:8100")
    user_id = state.get("user_id")
    phone = state.get("user_phone")

    try:
        result = await oms_tools.search_orders(
            user_id=user_id,
            phone=phone,
            auth_token=state.get("auth_token"),
            base_url=base_url,
        )
        orders = result.get("orders", [])
    except Exception as e:
        return {
            "messages": [AIMessage(content=f"❌ Sorry, I couldn't fetch your orders. Error: {str(e)}")],
            "orders": [],
            "last_updated_at": time.time(),
        }

    if not orders:
        return {
            "messages": [AIMessage(content="📦 You don't have any orders yet. Is there anything else I can help with?")],
            "orders": [],
            "current_flow": None,
            "last_updated_at": time.time(),
        }

    return {
        "orders": orders,
        "current_flow": "orders",
        "last_updated_at": time.time(),
    }


def show_orders(state: ConversationState) -> dict:
    """Show the list of orders and let the user pick one."""
    orders = state.get("orders", [])

    if not orders:
        msg = "📦 No orders found. Returning to main menu."
        return {
            "messages": [AIMessage(content=msg)],
            "last_updated_at": time.time(),
        }

    # Build order list
    lines = ["📦 Here are your recent orders:\n"]
    for i, order in enumerate(orders, 1):
        status_emoji = {
            "pre_dispatch": "🟡",
            "preparing": "🟡",
            "shipped": "🚚",
            "out_for_delivery": "🏃",
            "delivered": "✅",
            "cancelled": "❌",
            "return_initiated": "🔄",
        }.get(order.get("fulfillment_status", ""), "📋")

        lines.append(
            f"{i}. {status_emoji} **{order['id']}** — {order.get('first_item_name', 'Order')}\n"
            f"   Status: {order.get('status', 'Unknown').replace('_', ' ').title()} | "
            f"Total: ₹{order.get('total', 0):.0f}"
        )

    lines.append("\nPlease select an order (enter the number):")
    menu_text = "\n".join(lines)

    selection = interrupt(menu_text)

    # Parse selection
    try:
        idx = int(selection.strip()) - 1
        if 0 <= idx < len(orders):
            selected = orders[idx]
        else:
            selected = orders[0]
    except (ValueError, IndexError):
        # Try matching order ID
        selected = None
        for o in orders:
            if o["id"].lower() in selection.strip().lower():
                selected = o
                break
        if not selected:
            selected = orders[0]

    return {
        "messages": [AIMessage(content=menu_text)],
        "selected_order_id": selected["id"],
        "selected_order": selected,
        "order_status": _normalize_status(selected.get("fulfillment_status", "")),
        "last_updated_at": time.time(),
    }


def route_by_status(state: ConversationState) -> str:
    """Conditional edge: route based on order_status."""
    status = state.get("order_status", "")
    route_map = {
        "pre_dispatch": "pre_dispatch_menu",
        "shipped": "shipped_menu",
        "out_for_delivery": "shipped_menu",
        "delivery_failed": "shipped_menu",
        "delivered": "delivered_menu",
        "cancelled": "cancelled_status",
        "return_initiated": "return_initiated_status",
    }
    return route_map.get(status, "pre_dispatch_menu")
