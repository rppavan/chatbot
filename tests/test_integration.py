"""
Integration tests for the CX chatbot.
Tests end-to-end flows against the dummy API.
"""
import asyncio
import httpx
import pytest
import subprocess
import time
import signal
import os
import sys

BASE_URL = "http://localhost:8000"
DUMMY_API_URL = "http://localhost:8100"
HEADERS = {"X-Tenant-Id": "store-a"}


async def chat(message: str, session_id: str = "test-session-001") -> dict:
    """Send a chat message and return the response."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BASE_URL}/chat",
            json={"message": message, "session_id": session_id},
            headers=HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


async def chat_flow(messages: list[str], session_id: str = "test-session-001") -> list[dict]:
    """Send a sequence of chat messages and collect all responses."""
    results = []
    for msg in messages:
        result = await chat(msg, session_id)
        results.append(result)
        print(f"  User: {msg}")
        for r in result.get("responses", []):
            print(f"  Bot:  {r[:100]}...")
        print()
    return results


class TestHealthCheck:
    """Test that both services are running."""

    @pytest.mark.asyncio
    async def test_chatbot_health(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_dummy_api_health(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DUMMY_API_URL}/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"


class TestDummyAPI:
    """Test the dummy API endpoints directly."""

    @pytest.mark.asyncio
    async def test_order_search(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DUMMY_API_URL}/v1/order-search", params={"user_id": "user-001"})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["orders"]) > 0

    @pytest.mark.asyncio
    async def test_get_order(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DUMMY_API_URL}/v1/order/ORD-10001")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == "ORD-10001"

    @pytest.mark.asyncio
    async def test_tracking_summary(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DUMMY_API_URL}/v1/order/ORD-10002/tracking-summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "shipped"
            assert data["awb"] is not None

    @pytest.mark.asyncio
    async def test_cancel_options(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DUMMY_API_URL}/v1/order/ORD-10001/cancel_options")
            assert resp.status_code == 200
            data = resp.json()
            assert data["can_cancel"] is True

    @pytest.mark.asyncio
    async def test_return_options(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DUMMY_API_URL}/v1/order/ORD-10004/return-options")
            assert resp.status_code == 200
            data = resp.json()
            assert data["can_return"] is True

    @pytest.mark.asyncio
    async def test_exchange_options(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DUMMY_API_URL}/v1/order/ORD-10004/exchange-options")
            assert resp.status_code == 200
            data = resp.json()
            assert data["can_exchange"] is True
            assert len(data["available_variants"]) > 0

    @pytest.mark.asyncio
    async def test_login_otp(self):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{DUMMY_API_URL}/v2/user/auth/login/otp",
                json={"phone": "+919876543210"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["is_registered"] is True

    @pytest.mark.asyncio
    async def test_user_profile(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DUMMY_API_URL}/v2/user/user-001/profile")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "Priya Sharma"

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test cancellation (resets data for next test run)."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{DUMMY_API_URL}/v1/order/ORD-10001/cancel",
                json={"reason": "Test cancellation"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True


class TestChatEndpoint:
    """Test the chat endpoint basic functionality."""

    @pytest.mark.asyncio
    async def test_initial_message(self):
        """Test that sending a message starts the conversation."""
        result = await chat("Hi", session_id="test-init-001")
        assert "responses" in result
        assert len(result["responses"]) > 0

    @pytest.mark.asyncio
    async def test_session_isolation(self):
        """Test that different sessions are isolated."""
        result1 = await chat("Hello", session_id="test-iso-001")
        result2 = await chat("Hello", session_id="test-iso-002")
        # Both should get responses (independent sessions)
        assert len(result1["responses"]) > 0
        assert len(result2["responses"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
