"""
OMS Tools — thin wrappers that delegate to the backend router.
Graph nodes call these functions; the router selects MockBackend or ChatServiceBackend.
"""
from src.backends.router import get_backend


async def search_orders(
    tenant_id: str,
    user_id: str | None = None,
    phone: str | None = None,
    auth_token: str | None = None,
) -> dict:
    """Search orders by user_id or phone number."""
    backend = get_backend(tenant_id)
    return await backend.search_orders(phone=phone, user_id=user_id)


async def get_order(
    tenant_id: str,
    order_id: str,
    auth_token: str | None = None,
) -> dict:
    """Get full order details by order ID."""
    backend = get_backend(tenant_id)
    return await backend.get_order(order_id)


async def get_tracking_summary(
    tenant_id: str,
    order_id: str,
    line_item_id: str | None = None,
    auth_token: str | None = None,
) -> dict:
    """Get tracking summary for an order."""
    backend = get_backend(tenant_id)
    return await backend.get_tracking(order_id, line_item_id=line_item_id)


async def get_cancel_options(
    tenant_id: str,
    order_id: str,
    auth_token: str | None = None,
) -> dict:
    """Get cancellation options for an order."""
    backend = get_backend(tenant_id)
    return await backend.get_cancel_options(order_id)


async def cancel_order(
    tenant_id: str,
    order_id: str,
    reason: str = "Customer requested cancellation",
    auth_token: str | None = None,
) -> dict:
    """Cancel an order."""
    backend = get_backend(tenant_id)
    return await backend.cancel_order(order_id, reason)


async def get_return_options(
    tenant_id: str,
    order_id: str,
    auth_token: str | None = None,
) -> dict:
    """Get return options for an order."""
    backend = get_backend(tenant_id)
    return await backend.get_return_options(order_id)


async def initiate_return(
    tenant_id: str,
    order_id: str,
    reason: str = "Product not as expected",
    auth_token: str | None = None,
) -> dict:
    """Initiate a return for an order."""
    backend = get_backend(tenant_id)
    return await backend.initiate_return(order_id, reason)


async def get_exchange_options(
    tenant_id: str,
    order_id: str,
    auth_token: str | None = None,
) -> dict:
    """Get exchange options for an order."""
    backend = get_backend(tenant_id)
    return await backend.get_exchange_options(order_id)


async def initiate_exchange(
    tenant_id: str,
    order_id: str,
    new_variant_id: str,
    reason: str = "Size/Color change",
    auth_token: str | None = None,
) -> dict:
    """Initiate an exchange for an order."""
    backend = get_backend(tenant_id)
    return await backend.initiate_exchange(order_id, new_variant_id, reason)
