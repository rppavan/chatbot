"""
Core chat processing logic — shared by the HTTP endpoint and channel integrations.
"""
import time
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from pydantic import BaseModel

from src.config import load_tenant_config, MOCK_API_BASE_URL, DEFAULT_TENANT_ID
from src.tools.user_tools import get_profile, lookup_user_by_phone


# ─── Graph reference (set once at startup via setup()) ──────────────────
_graph = None


def setup(graph) -> None:
    """Bind the compiled graph. Called once during FastAPI lifespan startup."""
    global _graph
    _graph = graph


# ─── Response model ──────────────────────────────────────────────────────
class ChatResponse(BaseModel):
    session_id: str
    responses: list[str]
    is_escalated: bool = False
    awaiting_input: bool = False


# ─── Core processor ─────────────────────────────────────────────────────
async def process_chat(
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    session_id: str,
    user_id: Optional[str] = None,
    user_phone: Optional[str] = None,
    message: str,
    channel: str = "web",
) -> ChatResponse:
    """
    Process a single chat turn. Resumes an existing session or starts a fresh one.

    Args:
        tenant_id:  Tenant identifier — maps to a TENANT_CONFIGS entry.
        session_id: Unique session / conversation identifier.
        user_id:    Pre-authenticated user ID injected by the API gateway (skips OTP).
        user_phone: Pre-authenticated phone injected by the API gateway (skips OTP).
        message:    The user's message text.
        channel:    Channel name ("web", "whatsapp", …).
    """
    if not _graph:
        return ChatResponse(
            session_id=session_id,
            responses=["Service is starting up. Please try again in a moment."],
        )

    config = {"configurable": {"thread_id": f"{tenant_id}:{session_id}"}}

    # ── Load existing state snapshot ─────────────────────────────────────
    try:
        snapshot = await _graph.aget_state(config)
    except Exception:
        snapshot = None

    # ── Short-circuit for escalated sessions ─────────────────────────────
    if snapshot and snapshot.values and snapshot.values.get("is_escalated"):
        ticket_id = snapshot.values.get("freshdesk_ticket_id", "N/A")
        return ChatResponse(
            session_id=session_id,
            responses=[
                f"Your conversation is currently being handled by a support agent. "
                f"Ticket ID: #{ticket_id}. Please wait for their response."
            ],
            is_escalated=True,
        )

    # ── TTL invalidation (1 hour) ─────────────────────────────────────────
    if snapshot and snapshot.values and snapshot.values.get("last_updated_at"):
        if (time.time() - snapshot.values["last_updated_at"]) > 3600:
            snapshot = None

    # ── Count existing AI messages to extract only new ones later ─────────
    prior_ai_count = 0
    if snapshot and snapshot.values and "messages" in snapshot.values:
        prior_ai_count = sum(
            1 for m in snapshot.values["messages"] if isinstance(m, AIMessage)
        )

    # ── Invoke graph ──────────────────────────────────────────────────────
    try:
        if snapshot and snapshot.next:
            # Resume from interrupt
            result = await _graph.ainvoke(Command(resume=message), config=config)
        else:
            # Fresh session
            tenant_config = load_tenant_config(tenant_id)
            base_url = tenant_config.get("api_base_url", MOCK_API_BASE_URL)

            initial_state = {
                "messages": [HumanMessage(content=message)],
                "tenant_id": tenant_id,
                "tenant_config": tenant_config,
                "channel": channel,
                "channel_identifier": session_id,
                "session_id": session_id,
                "is_authenticated": False,
                "otp_requested": False,
                "is_escalated": False,
                "csat_collected": False,
                "last_updated_at": time.time(),
            }

            # API gateway injects identity — skip OTP when present
            if user_id:
                try:
                    profile = await get_profile(user_id, base_url=base_url)
                    initial_state["is_authenticated"] = True
                    initial_state["user_id"] = user_id
                    initial_state["user_name"] = profile.get("name")
                    initial_state["user_phone"] = profile.get("phone")
                except Exception:
                    pass  # Fall through to OTP flow if profile fetch fails
            elif user_phone:
                initial_state["is_authenticated"] = True
                initial_state["user_phone"] = user_phone
                try:
                    users = await lookup_user_by_phone(user_phone, base_url=base_url)
                    if users:
                        initial_state["user_id"] = users[0]["id"]
                        initial_state["user_name"] = users[0].get("name")
                except Exception:
                    pass

            result = await _graph.ainvoke(initial_state, config=config)

    except Exception as e:
        logging.exception("Graph invocation failed for session %s", session_id)
        return ChatResponse(
            session_id=session_id,
            responses=["I'm sorry, something went wrong. Please try again."],
        )

    # ── Extract new AI messages from this turn ────────────────────────────
    responses = []
    if result and "messages" in result:
        ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage) and m.content]
        responses = [m.content for m in ai_messages[prior_ai_count:]]

    # ── Append interrupt prompt if the graph is waiting for input ─────────
    awaiting_input = False
    try:
        new_snapshot = await _graph.aget_state(config)
        if new_snapshot and new_snapshot.tasks:
            for task in new_snapshot.tasks:
                for intr in task.interrupts:
                    if intr.value:
                        responses.append(str(intr.value))
                        awaiting_input = True
    except Exception:
        pass

    if not responses:
        responses = ["I'm here to help! Please type your message."]

    return ChatResponse(
        session_id=session_id,
        responses=responses,
        is_escalated=result.get("is_escalated", False) if result else False,
        awaiting_input=awaiting_input,
    )
