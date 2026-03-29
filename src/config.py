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

# --- Shopify / Clickpost (chat_service backend) ---
ORDERS_MONTHS_LIMIT = int(os.getenv("ORDERS_MONTHS_LIMIT", "6"))


# --- Tenant Configurations ---
TENANT_CONFIGS = {
    "store-a": {
        "store_name": "UrbanStyle",
        "backend_type": "mock",
        "api_base_url": MOCK_API_BASE_URL,
        "support_email": "support@urbanstyle.com",
        "support_phone": "+911234567890",
        "return_window_days": 7,
        "exchange_window_days": 7,
    },
    "store-b": {
        "store_name": "TechGadgets",
        "backend_type": "mock",
        "api_base_url": MOCK_API_BASE_URL,
        "support_email": "help@techgadgets.com",
        "support_phone": "+910987654321",
        "return_window_days": 15,
        "exchange_window_days": 15,
    },
    "nobero": {
        "store_name": "Nobero",
        "backend_type": "chat_service",
        "shopify_shop_name": os.getenv("SHOPIFY_SHOP_NAME", ""),
        "shopify_access_token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
        "clickpost_username": os.getenv("CLICKPOST_USERNAME", ""),
        "clickpost_api_key": os.getenv("CLICKPOST_API_KEY", ""),
        "support_email": "support@nobero.com",
        "support_phone": "+91...",
        "return_window_days": 7,
        "exchange_window_days": 7,
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
