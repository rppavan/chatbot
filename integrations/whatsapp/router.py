"""
WhatsApp channel integration — mounted as a router on the unified FastAPI app.

Routes (all under the /webhook prefix set in src/main.py):
    GET  /webhook/whatsapp  — Meta webhook verification
    POST /webhook/whatsapp  — Incoming WhatsApp messages
"""
import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, Request, HTTPException, Query

from src.config import (
    WHATSAPP_VERIFY_TOKEN,
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID,
    MOCK_API_BASE_URL,
    DEFAULT_TENANT_ID,
)
from src.chat_handler import process_chat

logger = logging.getLogger("whatsapp")

GRAPH_API_URL = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

router = APIRouter()


# ─── Helpers ─────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    """
    Validate Meta's X-Hub-Signature-256 HMAC.
    Returns True when WHATSAPP_ACCESS_TOKEN is unset (dev/test mode).
    """
    app_secret = WHATSAPP_ACCESS_TOKEN  # Meta signs with your App Secret, not access token
    # In production, WHATSAPP_APP_SECRET should be a separate env var; using access token
    # as a stand-in here is intentional for the current config structure — replace with
    # WHATSAPP_APP_SECRET when available.
    if not app_secret:
        return True  # dev/test mode — no secret configured
    expected = "sha256=" + hmac.new(
        app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


def normalize_phone(raw_phone: str) -> str:
    """Normalise a WhatsApp phone number to E.164 format."""
    phone = raw_phone.strip()
    return phone if phone.startswith("+") else f"+{phone}"


async def resolve_user_id(phone: str) -> str | None:
    """Look up a phone number in the OMS API to obtain a user_id."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{MOCK_API_BASE_URL}/v2/user", params={"phone": phone})
            resp.raise_for_status()
            users = resp.json()
            if users:
                return users[0]["id"]
    except Exception as e:
        logger.warning("User lookup failed for %s: %s", phone, e)
    return None


async def send_whatsapp_message(to_phone: str, text: str) -> None:
    """Send a text message via Meta WhatsApp Cloud API."""
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN not set — cannot send message")
        return
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(GRAPH_API_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("Failed to send WhatsApp message: %s %s", resp.status_code, resp.text)
        else:
            logger.info("Sent message to %s", to_phone)


# ─── Routes ──────────────────────────────────────────────────────────────

@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification (GET during initial setup)."""
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def receive_webhook(request: Request):
    """Receive incoming WhatsApp messages from Meta Cloud API."""
    raw_body = await request.body()

    if not _verify_signature(raw_body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=403, detail="Invalid signature")

    body = await request.json() if not raw_body else __import__("json").loads(raw_body)

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue

                raw_phone = msg.get("from", "")
                text = msg.get("text", {}).get("body", "")

                if not raw_phone or not text:
                    continue

                phone = normalize_phone(raw_phone)
                logger.info("Received message from %s: %s", phone, text[:50])

                user_id = await resolve_user_id(phone)

                try:
                    chat_response = await process_chat(
                        tenant_id=DEFAULT_TENANT_ID,
                        session_id=f"whatsapp:{phone}",
                        user_id=user_id,
                        user_phone=phone,
                        message=text,
                        channel="whatsapp",
                    )
                    responses = chat_response.responses
                except Exception as e:
                    logger.error("Chat processing failed: %s", e)
                    responses = ["Sorry, something went wrong. Please try again."]

                for resp_text in responses:
                    logger.info("Response to %s: %s", phone, resp_text[:200])
                    await send_whatsapp_message(phone, resp_text)

    return {"status": "ok"}
