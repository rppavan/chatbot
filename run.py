"""
Unified entry point — runs the chatbot and all integrations in a single process.

Usage: python run.py
"""
import asyncio

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from src.main import app as chatbot_app
from src.config import CHATBOT_PORT
from integrations.whatsapp.app import app as whatsapp_app, WHATSAPP_PORT


async def main():
    chatbot_server = uvicorn.Server(
        uvicorn.Config(chatbot_app, host="0.0.0.0", port=CHATBOT_PORT, log_level="info"),
    )
    whatsapp_server = uvicorn.Server(
        uvicorn.Config(whatsapp_app, host="0.0.0.0", port=WHATSAPP_PORT, log_level="info"),
    )

    print(f"Starting chatbot on :{CHATBOT_PORT} and WhatsApp webhook on :{WHATSAPP_PORT}")
    await asyncio.gather(
        chatbot_server.serve(),
        whatsapp_server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
