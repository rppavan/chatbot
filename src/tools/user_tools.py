"""
User Tools — HTTP client wrappers for user/auth API calls.

OTP/auth functions are mock-specific and keep base_url.
lookup_user_by_phone routes through the backend router.
"""
import httpx
from src.config import MOCK_API_BASE_URL


async def request_login_otp(
    phone: str,
    base_url: str = MOCK_API_BASE_URL,
) -> dict:
    """Request OTP for login."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{base_url}/v2/user/auth/login/otp", json={"phone": phone})
        resp.raise_for_status()
        return resp.json()


async def verify_login_otp(
    phone: str,
    otp: str,
    base_url: str = MOCK_API_BASE_URL,
) -> dict:
    """Verify OTP and get auth token + user info."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/v2/user/auth/verify-otp",
            json={"phone": phone, "otp": otp},
        )
        resp.raise_for_status()
        return resp.json()


async def get_profile(
    user_id: str,
    auth_token: str | None = None,
    base_url: str = MOCK_API_BASE_URL,
) -> dict:
    """Get user profile."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/v2/user/{user_id}/profile", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def lookup_user_by_phone(
    phone: str,
    tenant_id: str | None = None,
    base_url: str = MOCK_API_BASE_URL,
) -> list[dict]:
    """
    Look up users by phone number.

    Routes through the backend router when tenant_id is provided (supports
    both mock and Shopify tenants). Falls back to direct mock API call when
    tenant_id is absent (legacy / WhatsApp without tenant context).
    """
    if tenant_id:
        from src.backends.router import get_backend
        backend = get_backend(tenant_id)
        user = await backend.get_user_by_phone(phone)
        return [user] if user else []

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/v2/user", params={"phone": phone})
        resp.raise_for_status()
        return resp.json()


async def get_addresses(
    user_id: str,
    auth_token: str | None = None,
    base_url: str = MOCK_API_BASE_URL,
) -> dict:
    """Get user addresses."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/v2/user/{user_id}/address", headers=headers)
        resp.raise_for_status()
        return resp.json()
