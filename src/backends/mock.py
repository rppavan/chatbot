"""
MockBackend — wraps the mock e-commerce API (store-a, store-b tenants).
Moves all httpx logic out of oms_tools/user_tools into one place.
"""
import httpx

from src.backends.base import BackendAdapter


class MockBackend(BackendAdapter):
    """Routes to the mock e-commerce API (development/testing tenants)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self._base_url = config.get("api_base_url", "http://localhost:8100")

    def _headers(self, auth_token: str | None = None) -> dict:
        if auth_token:
            return {"Authorization": f"Bearer {auth_token}"}
        return {}

    # ── Read operations ────────────────────────────────────────────────────

    async def get_user_by_phone(self, phone: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/v2/user", params={"phone": phone}
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                user = data[0]
                return {
                    "user_id": user.get("id", ""),
                    "phone": phone,
                    "email": user.get("email", ""),
                    "name": user.get("name", ""),
                }
            return {}

    async def search_orders(
        self,
        phone: str | None = None,
        user_id: str | None = None,
        auth_token: str | None = None,
    ) -> dict:
        params = {}
        if user_id:
            params["user_id"] = user_id
        if phone:
            params["phone"] = phone
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/v1/order-search",
                params=params,
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_order(
        self, order_id: str, auth_token: str | None = None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/v1/order/{order_id}",
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_tracking(
        self,
        order_id: str,
        line_item_id: str | None = None,
        auth_token: str | None = None,
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/v1/order/{order_id}/tracking-summary",
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    # ── Write operations ───────────────────────────────────────────────────

    async def get_cancel_options(
        self, order_id: str, auth_token: str | None = None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/v1/order/{order_id}/cancel_options",
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def cancel_order(
        self, order_id: str, reason: str, auth_token: str | None = None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/v1/order/{order_id}/cancel",
                json={"reason": reason},
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_return_options(
        self, order_id: str, auth_token: str | None = None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/v1/order/{order_id}/return-options",
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def initiate_return(
        self, order_id: str, reason: str, auth_token: str | None = None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/v1/order/{order_id}/return",
                json={"reason": reason},
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_exchange_options(
        self, order_id: str, auth_token: str | None = None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/v1/order/{order_id}/exchange-options",
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def initiate_exchange(
        self,
        order_id: str,
        new_variant_id: str,
        reason: str,
        auth_token: str | None = None,
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/v1/order/{order_id}/exchange",
                json={"reason": reason, "new_variant_id": new_variant_id},
                headers=self._headers(auth_token),
            )
            resp.raise_for_status()
            return resp.json()
