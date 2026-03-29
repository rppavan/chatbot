"""
FastAPI application — unified entry point for the CX chatbot and channel integrations.
Run: python -m src.main
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

import aiosqlite
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.config import SQLITE_DB_PATH, CHATBOT_PORT, DEFAULT_TENANT_ID
from src.graph.builder import build_graph
from src.chat_handler import setup as setup_chat, process_chat, ChatResponse


# ─── Lifespan ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the LangGraph graph with its SQLite checkpointer."""
    db_conn = await aiosqlite.connect(SQLITE_DB_PATH)
    checkpointer = AsyncSqliteSaver(conn=db_conn)
    await checkpointer.setup()
    graph = build_graph(checkpointer=checkpointer)
    setup_chat(graph)
    logging.info("Chatbot graph initialized with SQLite checkpointer at %s", SQLITE_DB_PATH)
    yield
    await db_conn.close()


app = FastAPI(
    title="E-commerce CX Chatbot",
    description="Multi-tenant customer support chatbot powered by LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount channel integrations
from integrations.whatsapp.router import router as whatsapp_router  # noqa: E402
app.include_router(whatsapp_router, prefix="/webhook", tags=["whatsapp"])


# ─── Request model ────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    channel: Optional[str] = "web"


# ─── Chat endpoint ────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """
    Main chat endpoint.

    Headers (injected by the API gateway after authentication):
        X-Tenant-Id:          Tenant identifier (defaults to 'store-a')
        X-TMRW-User-Session:  Session identifier (required)
        X-TMRW-User-Id:       Authenticated user ID — skips OTP when present
        X-TMRW-User-Phone:    Authenticated phone number — skips OTP when present
    """
    tenant_id = request.headers.get("x-tenant-id", DEFAULT_TENANT_ID)
    session_id = request.headers.get("x-tmrw-user-session")
    user_id = request.headers.get("x-tmrw-user-id")
    user_phone = request.headers.get("x-tmrw-user-phone")

    if not session_id:
        raise HTTPException(status_code=400, detail="Missing required header: x-tmrw-user-session")

    return await process_chat(
        tenant_id=tenant_id,
        session_id=session_id,
        user_id=user_id,
        user_phone=user_phone,
        message=body.message,
        channel=body.channel or "web",
    )


# ─── Health ───────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    from src.chat_handler import _graph
    return {"status": "ok", "service": "chatbot", "graph_ready": _graph is not None}


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=CHATBOT_PORT, reload=True)
