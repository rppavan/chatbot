"""
Welcome and main menu nodes.
"""
import time
from langchain_core.messages import AIMessage
from src.nodes import interrupt

from src.state import ConversationState
from src.llm.intent import classify_intent


MAIN_MENU_OPTIONS = [
    "I need help with my orders",
    "Other Issues / FAQs",
]


def welcome(state: ConversationState) -> dict:
    """
    Welcome node: greet the user by name and show main menu.
    """
    name = state.get("user_name", "there")
    store_name = state.get("tenant_config", {}).get("store_name", "our store")

    welcome_msg = (
        f"👋 Hi {name}! Welcome to {store_name}.\n\n"
        f"How can I help you today?\n\n"
        f"1️⃣ I need help with my orders\n"
        f"2️⃣ Other Issues / FAQs"
    )

    return {
        "messages": [AIMessage(content=welcome_msg)],
        "current_flow": None,
        "last_updated_at": time.time(),
    }


def main_menu(state: ConversationState) -> dict:
    """
    Main menu node: wait for user selection and route accordingly.
    """
    menu_text = (
        "Please choose an option:\n\n"
        "1️⃣ I need help with my orders\n"
        "2️⃣ Other Issues / FAQs\n\n"
        "Type a number or describe what you need:"
    )
    user_input = interrupt(menu_text)

    return {
        "messages": [],
        "awaiting_input": None,
        "extracted_slots": {"menu_selection": user_input.strip()},
        "last_updated_at": time.time(),
    }


async def route_main_menu(state: ConversationState) -> str:
    """Conditional edge: route based on main menu selection."""
    selection = state.get("extracted_slots", {}).get("menu_selection", "")

    # Try direct number match first
    if selection in ("1", "1️⃣"):
        return "fetch_orders"
    if selection in ("2", "2️⃣"):
        return "faq_categories"

    # Use LLM intent classification for free-text
    intent = await classify_intent(selection, MAIN_MENU_OPTIONS)

    if "orders" in intent.lower():
        return "fetch_orders"
    if "faq" in intent.lower() or "other" in intent.lower() or "issue" in intent.lower():
        return "faq_categories"

    # Default to orders flow
    return "fetch_orders"
