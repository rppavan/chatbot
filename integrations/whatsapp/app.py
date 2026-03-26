"""
WhatsApp integration service — translates Meta Cloud API webhooks
to chatbot requests and sends responses back via WhatsApp.

Run: python -m integrations.whatsapp.app
"""
import os
import logging

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Query

load_dotenv()

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_PORT = int(os.getenv("WHATSAPP_PORT", "8200"))
CHATBOT_BASE_URL = os.getenv("CHATBOT_BASE_URL", "http://localhost:8000")
MOCK_API_BASE_URL = os.getenv("MOCK_API_BASE_URL", "http://localhost:8100")
DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "store-a")

GRAPH_API_URL = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

logger = logging.getLogger("whatsapp")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="WhatsApp Integration", version="1.0.0")


# ─── Helpers ─────────────────────────────────────────────────────────────


async def resolve_user_id(phone: str) -> str | None:
    """Look up phone number in the mock API to get a user_id."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MOCK_API_BASE_URL}/v2/user",
                params={"phone": phone},
            )
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
        logger.error("WHATSAPP_ACCESS_TOKEN is not set — cannot send message")
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
    async with httpx.AsyncClient() as client:
        resp = await client.post(GRAPH_API_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("Failed to send WhatsApp message: %s %s", resp.status_code, resp.text)
        else:
            logger.info("Sent message to %s", to_phone)


async def forward_to_chatbot(phone: str, message: str, user_id: str | None) -> list[str]:
    """Forward a user message to the chatbot and return the response texts."""
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-Id": DEFAULT_TENANT_ID,
        "X-TMRW-User-Session": f"whatsapp:{phone}",
        "X-TMRW-User-Phone": phone,
    }
    if user_id:
        headers["X-TMRW-User-Id"] = user_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{CHATBOT_BASE_URL}/chat",
            json={"message": message},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("responses", [])


def normalize_phone(raw_phone: str) -> str:
    """Normalize WhatsApp phone number to E.164 format with + prefix."""
    phone = raw_phone.strip()
    if not phone.startswith("+"):
        phone = f"+{phone}"
    return phone


# ─── Webhook Endpoints ──────────────────────────────────────────────────


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification (GET request during setup)."""
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Receive incoming WhatsApp messages from Meta Cloud API."""
    body = await request.json()

    # Navigate the Meta webhook payload structure
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])

            for msg in messages:
                if msg.get("type") != "text":
                    continue

                raw_phone = msg.get("from", "")
                text = msg.get("text", {}).get("body", "")

                if not raw_phone or not text:
                    continue

                phone = normalize_phone(raw_phone)
                logger.info("Received message from %s: %s", phone, text[:50])

                # Resolve phone → user_id
                user_id = await resolve_user_id(phone)

                # Forward to chatbot
                try:
                    responses = await forward_to_chatbot(phone, text, user_id)
                except Exception as e:
                    logger.error("Chatbot request failed: %s", e)
                    responses = ["Sorry, something went wrong. Please try again."]

                # Send each response back via WhatsApp
                for resp_text in responses:
                    logger.info("Response to %s: %s", phone, resp_text[:200])
                    await send_whatsapp_message(raw_phone, resp_text)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "whatsapp-integration"}


if __name__ == "__main__":
    uvicorn.run("integrations.whatsapp.app:app", host="0.0.0.0", port=WHATSAPP_PORT, reload=True)
