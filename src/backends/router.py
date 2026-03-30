"""
Backend router — selects the right BackendAdapter for a given tenant_id.
"""
from src.backends.base import BackendAdapter
from src.backends.mock import MockBackend
from src.backends.shopify import ShopifyBackend

_REGISTRY: dict[str, type[BackendAdapter]] = {
    "mock": MockBackend,
    "chat_service": ShopifyBackend,
}


def get_backend(tenant_id: str) -> BackendAdapter:
    """
    Return the BackendAdapter for the given tenant.
    Raises ValueError for unknown tenants.
    """
    from src.config import TENANT_CONFIGS  # local import to avoid circular deps

    config = TENANT_CONFIGS.get(tenant_id)
    if not config:
        raise ValueError(f"Unknown tenant: {tenant_id!r}")

    backend_type = config.get("backend_type", "mock")
    cls = _REGISTRY.get(backend_type)
    if not cls:
        raise ValueError(f"Unknown backend_type {backend_type!r} for tenant {tenant_id!r}")

    return cls({**config, "tenant_id": tenant_id})
