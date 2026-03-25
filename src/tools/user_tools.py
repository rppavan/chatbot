"""
User Tools — HTTP client wrappers for user/auth API calls.
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
