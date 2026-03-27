"""
Common nodes — CSAT survey and close chat (terminal nodes).
"""
import time
from langchain_core.messages import AIMessage
from src.nodes import interrupt

from src.state import ConversationState


def csat_survey(state: ConversationState) -> dict:
    """Collect CSAT rating before closing the chat."""
    if state.get("csat_collected"):
        return {}

    csat_msg = (
        "📊 Before we close, how would you rate your experience today?\n\n"
        "1️⃣ ⭐ Very Poor\n"
        "2️⃣ ⭐⭐ Poor\n"
        "3️⃣ ⭐⭐⭐ Average\n"
        "4️⃣ ⭐⭐⭐⭐ Good\n"
        "5️⃣ ⭐⭐⭐⭐⭐ Excellent\n\n"
        "Type a number (1-5) or 'skip' to close:"
    )

    user_input = interrupt(csat_msg)

    rating = user_input.strip()
    if rating.lower() == "skip":
        thank_msg = "Thank you for chatting with us! Have a great day! 👋"
    else:
        thank_msg = f"Thank you for your feedback (Rating: {rating})! Have a great day! 👋"

    return {
        "messages": [AIMessage(content=thank_msg)],
        "csat_collected": True,
        "last_updated_at": time.time(),
    }


def close_chat(state: ConversationState) -> dict:
    """Terminal node — close the chat session."""
    if not state.get("csat_collected"):
        msg = "Thank you for chatting with us! Have a great day! 👋"
    else:
        msg = "Chat closed. See you next time! 👋"

    return {
        "messages": [AIMessage(content=msg)],
        "last_updated_at": time.time(),
    }
