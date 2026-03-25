"""
Configuration management for the chatbot service.
"""
import os
from dotenv import load_dotenv

load_dotenv()


# --- Environment Settings ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DUMMY_API_BASE_URL = os.getenv("DUMMY_API_BASE_URL", "http://localhost:8100")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "chatbot_memory.db")
CHATBOT_PORT = int(os.getenv("CHATBOT_PORT", "8000"))


# --- Tenant Configurations ---
TENANT_CONFIGS = {
    "store-a": {
        "store_name": "UrbanStyle",
        "api_base_url": DUMMY_API_BASE_URL,
        "support_email": "support@urbanstyle.com",
        "support_phone": "+911234567890",
        "return_window_days": 7,
        "exchange_window_days": 7,
    },
    "store-b": {
        "store_name": "TechGadgets",
        "api_base_url": DUMMY_API_BASE_URL,
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
