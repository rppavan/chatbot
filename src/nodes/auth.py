"""
Auth nodes — user authentication and guest flow handling.
"""
import time
from langchain_core.messages import AIMessage
from src.nodes import interrupt

from src.state import ConversationState
from src.tools import user_tools


def check_user(state: ConversationState) -> dict:
    """
    Entry point node. Checks if user is authenticated.
    This is a pass-through that sets up routing via conditional edge.
    """
    return {}


def route_auth(state: ConversationState) -> str:
    """Conditional edge: route based on authentication status."""
    if state.get("is_authenticated"):
        return "welcome"
    return "guest_flow"


def route_handle_otp(state: ConversationState) -> str:
    """Route OTP handling based on verification outcome."""
    if state.get("is_authenticated"):
        return "welcome"
    return "handle_otp"


def guest_flow(state: ConversationState) -> dict:
    """
    Guest flow: prompt for phone number to authenticate via OTP.
    Uses interrupt() to pause and wait for user input.
    """
    # Ask for phone number
    phone_prompt = (
        "👋 Welcome! To assist you with your orders, I'll need to verify your identity.\n\n"
        "Please enter your phone number (e.g., +919876543210):"
    )
    user_input = interrupt(phone_prompt)

    # Store phone for OTP flow
    return {
        "messages": [],
        "user_phone": user_input.strip(),
        "awaiting_input": "otp",
        "otp_requested": False,
        "last_updated_at": time.time(),
    }


async def handle_otp(state: ConversationState) -> dict:
    """
    OTP sub-flow: verify an OTP that was already requested.
    """
    phone = state.get("user_phone", "")
    base_url = state.get("tenant_config", {}).get("api_base_url", "http://localhost:8100")

    otp_input = interrupt("Please enter the OTP:")
    otp_input = otp_input.strip()

    try:
        result = await user_tools.verify_login_otp(phone, otp_input, base_url=base_url)
    except Exception:
        return {
            "messages": [AIMessage(content="❌ OTP verification failed. Please try again.")],
            "otp_requested": True,
            "awaiting_input": "otp_verify",
            "last_updated_at": time.time(),
        }

    if result.get("success"):
        user_data = result.get("user", {})
        return {
            "messages": [AIMessage(content="✅ Verified successfully!")],
            "is_authenticated": True,
            "auth_token": result.get("token"),
            "user_id": user_data.get("id"),
            "user_name": user_data.get("name"),
            "user_phone": phone,
            "otp_requested": False,
            "awaiting_input": None,
            "last_updated_at": time.time(),
        }

    return {
        "messages": [AIMessage(content="❌ OTP verification failed. Please try again.")],
        "otp_requested": True,
        "awaiting_input": "otp_verify",
        "last_updated_at": time.time(),
    }


async def request_otp(state: ConversationState) -> dict:
    """Request a login OTP and prompt the user to enter it."""
    phone = state.get("user_phone", "")
    base_url = state.get("tenant_config", {}).get("api_base_url", "http://localhost:8100")

    result = await user_tools.request_login_otp(phone, base_url=base_url)
    debug_otp = result.get("debug_otp", "")

    otp_msg = f"📱 An OTP has been sent to {phone}.\nPlease enter the OTP to verify:"
    if debug_otp:
        otp_msg += f"\n\n(Debug OTP: {debug_otp})"

    return {
        "messages": [AIMessage(content=otp_msg)],
        "otp_requested": True,
        "otp_type": "login",
        "awaiting_input": "otp_verify",
        "last_updated_at": time.time(),
    }
