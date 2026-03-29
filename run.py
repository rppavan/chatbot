"""
Unified entry point — runs the chatbot and all channel integrations in a single process.

Usage: python run.py
"""
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from src.config import CHATBOT_PORT

if __name__ == "__main__":
    print(f"Starting unified chatbot service on :{CHATBOT_PORT}")
    uvicorn.run("src.main:app", host="0.0.0.0", port=CHATBOT_PORT, log_level="info")
