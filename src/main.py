"""
FastAPI application — Chat endpoint for the CX chatbot.
Run: python -m src.main
"""
import time
import asyncio
import logging
from contextlib import asynccontextmanager

import aiosqlite
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.state import ConversationState
from src.config import load_tenant_config, SQLITE_DB_PATH, CHATBOT_PORT, DEFAULT_TENANT_ID, MOCK_API_BASE_URL
from src.graph.builder import build_graph
from src.tools.user_tools import get_profile, lookup_user_by_phone


# ─── Global graph reference ─────────────────────────────────────────────
_graph = None
_checkpointer = None
_db_conn = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize graph with checkpointer on startup."""
    global _graph, _checkpointer, _db_conn
    _db_conn = await aiosqlite.connect(SQLITE_DB_PATH)
    _checkpointer = AsyncSqliteSaver(conn=_db_conn)
    await _checkpointer.setup()
    _graph = build_graph(checkpointer=_checkpointer)
    print(f"✅ Chatbot graph initialized with SQLite checkpointer at {SQLITE_DB_PATH}")
    yield
    # Cleanup
    if _db_conn:
        await _db_conn.close()


app = FastAPI(
    title="E-commerce CX Chatbot",
    description="Multi-tenant customer support chatbot powered by LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Request/Response Models ────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    channel: Optional[str] = "web"


class ChatResponse(BaseModel):
    session_id: str
    responses: list[str]
    is_escalated: bool = False
    awaiting_input: Optional[str] = None


# ─── Chat Endpoint ──────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """
    Main chat endpoint. Handles message routing, state resume, and response extraction.

    Headers:
        X-Tenant-Id: tenant identifier (defaults to 'store-a')
        X-TMRW-User-Session: session identifier (required)
        X-TMRW-User-Id: user identifier (optional — skips OTP when provided)
    """
    global _graph

    if not _graph:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")

    # Extract headers
    tenant_id = request.headers.get("x-tenant-id", DEFAULT_TENANT_ID)
    session_id = request.headers.get("x-tmrw-user-session")
    user_id = request.headers.get("x-tmrw-user-id")
    user_phone = request.headers.get("x-tmrw-user-phone")

    if not session_id:
        raise HTTPException(status_code=400, detail="Missing required header: X-TMRW-User-Session")

    user_message = body.message
    channel = body.channel or "web"

    # Build thread config for checkpointing
    config = {"configurable": {"thread_id": f"{tenant_id}:{session_id}"}}

    # Check existing state
    try:
        snapshot = await _graph.aget_state(config)
    except Exception:
        snapshot = None

    # Check if conversation is escalated (bypass graph)
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

    # Cache invalidation (TTL: 1 hour)
    if snapshot and snapshot.values and snapshot.values.get("last_updated_at"):
        if (time.time() - snapshot.values["last_updated_at"]) > 3600:
            # Session expired — start fresh
            snapshot = None

    try:
        # Determine if we're resuming an interrupted flow or starting fresh
        if snapshot and snapshot.next:
            # Resume from interrupt — pass user message as the resume value
            result = await _graph.ainvoke(
                Command(resume=user_message),
                config=config,
            )
        else:
            # Fresh invocation
            tenant_config = load_tenant_config(tenant_id)
            initial_state = {
                "messages": [HumanMessage(content=user_message)],
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

            # Pre-authenticate if user identity is provided via headers
            base_url = tenant_config.get("api_base_url", MOCK_API_BASE_URL)
            if user_id:
                # Direct user ID — fetch profile to populate name/phone
                try:
                    profile = await get_profile(user_id, base_url=base_url)
                    initial_state["is_authenticated"] = True
                    initial_state["user_id"] = user_id
                    initial_state["user_name"] = profile.get("name")
                    initial_state["user_phone"] = profile.get("phone")
                except Exception:
                    pass  # Fall through to normal OTP flow if profile fetch fails
            elif user_phone:
                # Phone number — look up user, or authenticate with phone alone
                initial_state["is_authenticated"] = True
                initial_state["user_phone"] = user_phone
                try:
                    users = await lookup_user_by_phone(user_phone, base_url=base_url)
                    if users:
                        initial_state["user_id"] = users[0]["id"]
                        initial_state["user_name"] = users[0].get("name")
                except Exception:
                    pass  # Authenticated by phone but no profile — still skip OTP

            result = await _graph.ainvoke(initial_state, config=config)
    except Exception as e:
        logging.exception("Graph invocation failed for session %s", session_id)
        return ChatResponse(
            session_id=session_id,
            responses=[f"I'm sorry, something went wrong. Please try again. (Error: {str(e)})"],
        )

    # Extract AI messages from result
    responses = []
    if result and "messages" in result:
        for msg in result["messages"]:
            if isinstance(msg, AIMessage) and msg.content:
                responses.append(msg.content)

    # If no responses were generated, check if the graph is waiting for input
    if not responses:
        # Check if graph is in interrupt state
        try:
            new_snapshot = await _graph.aget_state(config)
            if new_snapshot and new_snapshot.next:
                # Graph is waiting — the interrupt value contains the prompt
                # Return a generic prompt
                responses = ["How can I help you today?"]
        except Exception:
            pass

    if not responses:
        responses = ["I'm here to help! Please type your message."]

    return ChatResponse(
        session_id=session_id,
        responses=responses,
        is_escalated=result.get("is_escalated", False) if result else False,
        awaiting_input=result.get("awaiting_input") if result else None,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "chatbot", "graph_ready": _graph is not None}


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=CHATBOT_PORT, reload=True)
