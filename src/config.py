"""
Configuration management for the chatbot service.
"""
import os
from dotenv import load_dotenv

load_dotenv()


# --- Environment Settings ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
MOCK_API_BASE_URL = os.getenv("MOCK_API_BASE_URL", "http://localhost:8100")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "chatbot_memory.db")
CHATBOT_PORT = int(os.getenv("CHATBOT_PORT", "8000"))

# --- WhatsApp Integration ---
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")


# --- Tenant Configurations ---
TENANT_CONFIGS = {
    "store-a": {
        "store_name": "UrbanStyle",
        "api_base_url": MOCK_API_BASE_URL,
        "support_email": "support@urbanstyle.com",
        "support_phone": "+911234567890",
        "return_window_days": 7,
        "exchange_window_days": 7,
    },
    "store-b": {
        "store_name": "TechGadgets",
        "api_base_url": MOCK_API_BASE_URL,
        "support_email": "help@techgadgets.com",
        "support_phone": "+910987654321",
        "return_window_days": 15,
        "exchange_window_days": 15,
    },
}

# Default tenant for simplified testing
DEFAULT_TENANT_ID = "store-a"


def load_tenant_config(tenant_id: str) -> dict:
    """Load tenant-specific configuration by tenant_id."""
    config = TENANT_CONFIGS.get(tenant_id)
    if not config:
        # Fallback to default
        config = TENANT_CONFIGS[DEFAULT_TENANT_ID]
    return config
