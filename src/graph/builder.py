"""
LangGraph StateGraph builder — assembles all nodes and edges into the chatbot graph.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.state import ConversationState
from src.config import SQLITE_DB_PATH

# Import all node functions
from src.nodes.auth import check_user, route_auth, guest_flow, handle_otp
from src.nodes.welcome import welcome, main_menu, route_main_menu
from src.nodes.orders import fetch_orders, show_orders, route_by_status
from src.nodes.pre_dispatch import (
    pre_dispatch_menu, route_pre_dispatch,
    pre_dispatch_cancel, pre_dispatch_address, pre_dispatch_phone, pre_dispatch_modify,
)
from src.nodes.shipped import (
    shipped_menu, route_shipped,
    shipped_track, shipped_cancel, shipped_address,
)
from src.nodes.delivered import (
    delivered_menu, route_delivered,
    delivered_return, delivered_exchange,
    delivered_missing, delivered_wrong, delivered_not_received,
)
from src.nodes.other_status import cancelled_status, return_initiated_status
from src.nodes.faq import faq_categories, route_faq, faq_answer_node
from src.nodes.handoff import agent_handoff
from src.nodes.common import csat_survey, close_chat


def build_graph(checkpointer=None):
    """
    Build and compile the full chatbot StateGraph.

    Returns the compiled graph with all nodes and conditional edges.
    """
    builder = StateGraph(ConversationState)

    # ──────────────── Register Nodes ────────────────
    # Auth flow
    builder.add_node("check_user", check_user)
    builder.add_node("guest_flow", guest_flow)
    builder.add_node("handle_otp", handle_otp)

    # Welcome & main menu
    builder.add_node("welcome", welcome)
    builder.add_node("main_menu", main_menu)

    # Order flow
    builder.add_node("fetch_orders", fetch_orders)
    builder.add_node("show_orders", show_orders)

    # Pre-dispatch sub-tree
    builder.add_node("pre_dispatch_menu", pre_dispatch_menu)
    builder.add_node("pre_dispatch_cancel", pre_dispatch_cancel)
    builder.add_node("pre_dispatch_address", pre_dispatch_address)
    builder.add_node("pre_dispatch_phone", pre_dispatch_phone)
    builder.add_node("pre_dispatch_modify", pre_dispatch_modify)

    # Shipped sub-tree
    builder.add_node("shipped_menu", shipped_menu)
    builder.add_node("shipped_track", shipped_track)
    builder.add_node("shipped_cancel", shipped_cancel)
    builder.add_node("shipped_address", shipped_address)

    # Delivered sub-tree
    builder.add_node("delivered_menu", delivered_menu)
    builder.add_node("delivered_return", delivered_return)
    builder.add_node("delivered_exchange", delivered_exchange)
    builder.add_node("delivered_missing", delivered_missing)
    builder.add_node("delivered_wrong", delivered_wrong)
    builder.add_node("delivered_not_received", delivered_not_received)

    # Other statuses
    builder.add_node("cancelled_status", cancelled_status)
    builder.add_node("return_initiated_status", return_initiated_status)

    # FAQ flow
    builder.add_node("faq_categories", faq_categories)
    builder.add_node("faq_answer", faq_answer_node)

    # Agent handoff
    builder.add_node("agent_handoff", agent_handoff)

    # Common / terminal
    builder.add_node("csat_survey", csat_survey)
    builder.add_node("close_chat", close_chat)

    # ──────────────── Entry Point ────────────────
    builder.add_edge(START, "check_user")

    # ──────────────── Conditional Edges ────────────────

    # Auth routing: check_user → welcome (authenticated) or guest_flow (not)
    builder.add_conditional_edges("check_user", route_auth, {
        "welcome": "welcome",
        "guest_flow": "guest_flow",
    })

    # Guest flow → OTP verification
    builder.add_edge("guest_flow", "handle_otp")

    # OTP → welcome (on success, the graph will be re-invoked with is_authenticated=True)
    builder.add_edge("handle_otp", "welcome")

    # Welcome → main menu (wait for user selection)
    builder.add_edge("welcome", "main_menu")

    # Main menu routing
    builder.add_conditional_edges("main_menu", route_main_menu, {
        "fetch_orders": "fetch_orders",
        "faq_categories": "faq_categories",
    })

    # Order flow: fetch → show → route by status
    builder.add_edge("fetch_orders", "show_orders")
    builder.add_conditional_edges("show_orders", route_by_status, {
        "pre_dispatch_menu": "pre_dispatch_menu",
        "shipped_menu": "shipped_menu",
        "delivered_menu": "delivered_menu",
        "cancelled_status": "cancelled_status",
        "return_initiated_status": "return_initiated_status",
    })

    # Pre-dispatch routing
    builder.add_conditional_edges("pre_dispatch_menu", route_pre_dispatch, {
        "pre_dispatch_cancel": "pre_dispatch_cancel",
        "pre_dispatch_address": "pre_dispatch_address",
        "pre_dispatch_phone": "pre_dispatch_phone",
        "pre_dispatch_modify": "pre_dispatch_modify",
        "welcome": "welcome",
    })
    builder.add_edge("pre_dispatch_cancel", "csat_survey")
    builder.add_edge("pre_dispatch_address", "agent_handoff")
    builder.add_edge("pre_dispatch_phone", "agent_handoff")
    builder.add_edge("pre_dispatch_modify", "agent_handoff")

    # Shipped routing
    builder.add_conditional_edges("shipped_menu", route_shipped, {
        "shipped_track": "shipped_track",
        "shipped_cancel": "shipped_cancel",
        "shipped_address": "shipped_address",
        "welcome": "welcome",
    })
    builder.add_edge("shipped_track", "csat_survey")
    builder.add_edge("shipped_cancel", "csat_survey")
    builder.add_edge("shipped_address", "agent_handoff")

    # Delivered routing
    builder.add_conditional_edges("delivered_menu", route_delivered, {
        "delivered_return": "delivered_return",
        "delivered_exchange": "delivered_exchange",
        "delivered_missing": "delivered_missing",
        "delivered_wrong": "delivered_wrong",
        "delivered_not_received": "delivered_not_received",
        "welcome": "welcome",
    })
    builder.add_edge("delivered_return", "csat_survey")
    builder.add_edge("delivered_exchange", "csat_survey")
    builder.add_edge("delivered_missing", "agent_handoff")
    builder.add_edge("delivered_wrong", "agent_handoff")
    builder.add_edge("delivered_not_received", "agent_handoff")

    # Other statuses → CSAT
    builder.add_edge("cancelled_status", "csat_survey")
    builder.add_edge("return_initiated_status", "csat_survey")

    # FAQ routing
    builder.add_conditional_edges("faq_categories", route_faq, {
        "faq_answer": "faq_answer",
        "agent_handoff": "agent_handoff",
    })
    builder.add_edge("faq_answer", "csat_survey")

    # Agent handoff → CSAT
    builder.add_edge("agent_handoff", "csat_survey")

    # Terminal edges
    builder.add_edge("csat_survey", "close_chat")
    builder.add_edge("close_chat", END)

    # Compile with checkpointer
    graph = builder.compile(checkpointer=checkpointer)
    return graph


async def get_graph():
    """Get a compiled graph with SQLite checkpointer."""
    checkpointer = AsyncSqliteSaver.from_conn_string(SQLITE_DB_PATH)
    return build_graph(checkpointer=checkpointer)
