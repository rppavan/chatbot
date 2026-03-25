"""
Tracking Tools — HTTP client wrappers for tracking API calls.
"""
import httpx
from src.config import MOCK_API_BASE_URL


async def get_tracking_summary(
    order_id: str,
    auth_token: str | None = None,
    base_url: str = MOCK_API_BASE_URL,
) -> dict:
    """Get tracking summary for an order (delegates to OMS)."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base_url}/v1/order/{order_id}/tracking-summary",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()
