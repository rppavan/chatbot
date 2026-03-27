"""
FAQ flow nodes — category selection and answer generation.
"""
import time
from langchain_core.messages import AIMessage
from src.nodes import interrupt

from src.state import ConversationState
from src.llm.faq import answer_faq
from src.llm.intent import classify_intent


FAQ_CATEGORIES = [
    "Order, Delivery and Payment",
    "Cancellation Policy",
    "Refunds and Returns",
    "My Account",
    "Other Issues",
]

CATEGORY_MAP = {
    "Order, Delivery and Payment": "order_delivery_payment",
    "Cancellation Policy": "cancellation",
    "Refunds and Returns": "refunds_returns",
    "My Account": "my_account",
    "Other Issues": "other",
}


def faq_categories(state: ConversationState) -> dict:
    """Show FAQ category menu."""
    menu_text = (
        "📚 **FAQ Categories**\n\n"
        "1️⃣ Order, Delivery and Payment\n"
        "2️⃣ Cancellation Policy\n"
        "3️⃣ Refunds and Returns\n"
        "4️⃣ My Account\n"
        "5️⃣ Other Issues\n\n"
        "Select a category or type your question directly:"
    )

    user_input = interrupt(menu_text)

    return {
        "messages": [],
        "extracted_slots": {"faq_input": user_input.strip()},
        "current_flow": "faq",
        "last_updated_at": time.time(),
    }


async def route_faq(state: ConversationState) -> str:
    """Route FAQ selection — either to a category answer or agent handoff."""
    selection = state.get("extracted_slots", {}).get("faq_input", "")

    # Check if "Other Issues" → agent handoff
    if selection in ("5", "5️⃣"):
        return "agent_handoff"

    return "faq_answer"


async def faq_answer_node(state: ConversationState) -> dict:
    """Generate an FAQ answer using LLM."""
    selection = state.get("extracted_slots", {}).get("faq_input", "")
    store_name = state.get("tenant_config", {}).get("store_name", "our store")

    # Determine category
    category = None
    direct_map = {"1": "order_delivery_payment", "2": "cancellation", "3": "refunds_returns", "4": "my_account"}
    if selection in direct_map:
        category = direct_map[selection]
        question = f"Tell me about {FAQ_CATEGORIES[int(selection)-1].lower()}"
    else:
        # Try to match category by name
        for cat_name, cat_key in CATEGORY_MAP.items():
            if cat_name.lower() in selection.lower():
                category = cat_key
                break
        question = selection

    try:
        answer = await answer_faq(question, store_name, category=category)
    except Exception:
        answer = (
            "I'm sorry, I'm having trouble answering your question right now. "
            "Let me connect you with a support agent."
        )

    # Check for "can't answer" fallback
    if "unable to answer" in answer.lower() or "connect you with" in answer.lower():
        return {
            "messages": [AIMessage(content=answer)],
            "last_updated_at": time.time(),
        }

    # Ask if they need more help
    follow_up = f"{answer}\n\nDo you have any other questions? (type your question or 'main menu' to go back)"
    user_input = interrupt(follow_up)

    if user_input.strip().lower() in ("no", "main menu", "back", "done"):
        return {
            "messages": [],
            "last_updated_at": time.time(),
        }

    # Answer follow-up question
    try:
        follow_answer = await answer_faq(user_input.strip(), store_name)
    except Exception:
        follow_answer = "I'm sorry, I couldn't process that. Let me connect you with support."

    return {
        "messages": [AIMessage(content=follow_answer)],
        "last_updated_at": time.time(),
    }
