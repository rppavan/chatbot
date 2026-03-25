"""
OMS Tools — HTTP client wrappers for order management API calls.
These are called deterministically by graph nodes, not by the LLM agent.
"""
import httpx
from src.config import DUMMY_API_BASE_URL


async def search_orders(
    user_id: str | None = None,
    phone: str | None = None,
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Search orders by user_id or phone number."""
    params = {}
    if user_id:
        params["user_id"] = user_id
    if phone:
        params["phone"] = phone

    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/v1/order-search", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def get_order(
    order_id: str,
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Get full order details by order ID."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/v1/order/{order_id}", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def get_tracking_summary(
    order_id: str,
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Get tracking summary for an order."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/v1/order/{order_id}/tracking-summary", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def get_cancel_options(
    order_id: str,
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Get cancellation options for an order."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/v1/order/{order_id}/cancel_options", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def cancel_order(
    order_id: str,
    reason: str = "Customer requested cancellation",
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Cancel an order."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/v1/order/{order_id}/cancel",
            json={"reason": reason},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def get_return_options(
    order_id: str,
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Get return options for an order."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/v1/order/{order_id}/return-options", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def initiate_return(
    order_id: str,
    reason: str = "Product not as expected",
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Initiate a return for an order."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/v1/order/{order_id}/return",
            json={"reason": reason},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def get_exchange_options(
    order_id: str,
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Get exchange options for an order."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base_url}/v1/order/{order_id}/exchange-options", headers=headers
        )
        resp.raise_for_status()
        return resp.json()


async def initiate_exchange(
    order_id: str,
    new_variant_id: str,
    reason: str = "Size/Color change",
    auth_token: str | None = None,
    base_url: str = DUMMY_API_BASE_URL,
) -> dict:
    """Initiate an exchange for an order."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/v1/order/{order_id}/exchange",
            json={"reason": reason, "new_variant_id": new_variant_id},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()
