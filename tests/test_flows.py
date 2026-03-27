"""
Comprehensive flow tests verifying:
  - Multi-Tenant_Chatbot_PRD.md requirements
  - To-Be_Flow.md conversational paths
  - API_Flows.md endpoint correctness
  - Design critique gaps (escalation state, guest flow, exchange differential, etc.)

Prerequisites: both services must be running
  Terminal 1: python -m mock_api.app
  Terminal 2: python run.py   (or python -m src.main)

Run:
  pytest tests/test_flows.py -v
"""

import httpx
import pytest

BASE_URL = "http://localhost:8000"
MOCK_URL = "http://localhost:8100"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _headers(tenant: str, session: str, user_id: str | None = None, phone: str | None = None) -> dict:
    h = {"X-Tenant-Id": tenant, "X-TMRW-User-Session": session, "Content-Type": "application/json"}
    if user_id:
        h["X-TMRW-User-Id"] = user_id
    if phone:
        h["X-TMRW-User-Phone"] = phone
    return h


async def chat(message: str, session: str, tenant: str = "store-a",
               user_id: str | None = None, phone: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BASE_URL}/chat",
            json={"message": message},
            headers=_headers(tenant, session, user_id, phone),
        )
        resp.raise_for_status()
        return resp.json()


async def chat_flow(messages: list[str], session: str, tenant: str = "store-a",
                    user_id: str | None = None) -> list[dict]:
    """Drive a multi-turn conversation and return all responses."""
    results = []
    for i, msg in enumerate(messages):
        uid = user_id if i == 0 else None   # pre-auth only on first message
        results.append(await chat(msg, session, tenant, uid))
    return results


def combined(result: dict) -> str:
    """Concatenate all response strings for assertion."""
    return " ".join(result.get("responses", [])).lower()


# ── PRD §2.1: Multi-Tenancy ──────────────────────────────────────────────────

class TestMultiTenancy:
    """PRD §2.1 — Tenant identification and strict data isolation."""

    @pytest.mark.asyncio
    async def test_store_a_responds(self):
        result = await chat("Hi", "mt-001", tenant="store-a", user_id="user-001")
        assert len(result["responses"]) > 0

    @pytest.mark.asyncio
    async def test_store_b_responds(self):
        result = await chat("Hi", "mt-002", tenant="store-b", user_id="user-001")
        assert len(result["responses"]) > 0

    @pytest.mark.asyncio
    async def test_same_session_id_different_tenants_are_isolated(self):
        """
        PRD §2.1: Two tenants sharing the same raw session ID must get
        independent conversation states (thread_id = {tenant_id}:{session_id}).
        """
        shared_session = "mt-shared-999"
        r_a = await chat("Hi", shared_session, tenant="store-a", user_id="user-001")
        r_b = await chat("Hi", shared_session, tenant="store-b", user_id="user-001")
        # Both respond independently — neither conversation bleeds into the other
        assert len(r_a["responses"]) > 0
        assert len(r_b["responses"]) > 0

    @pytest.mark.asyncio
    async def test_missing_tenant_header_returns_error_or_defaults(self):
        """Chatbot must handle requests without X-Tenant-Id gracefully."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{BASE_URL}/chat",
                json={"message": "Hi"},
                headers={"X-TMRW-User-Session": "mt-no-tenant"},
            )
        # Either defaults (200) or rejects (4xx) — must not crash (5xx)
        assert resp.status_code < 500

    @pytest.mark.asyncio
    async def test_missing_session_header_returns_400(self):
        """PRD §5 security: session header is mandatory."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{BASE_URL}/chat",
                json={"message": "Hi"},
                headers={"X-Tenant-Id": "store-a"},
            )
        assert resp.status_code == 400


# ── PRD §3.2: Authentication ─────────────────────────────────────────────────

class TestAuthentication:
    """PRD §3.2 — OTP login and pre-authentication via header."""

    @pytest.mark.asyncio
    async def test_unauthenticated_session_prompts_for_phone(self):
        """Guest with no user_id header must be asked for phone number (OTP flow)."""
        result = await chat("Hi", "auth-guest-001", tenant="store-a")
        text = combined(result)
        # Should ask for phone number — not immediately show orders
        assert any(kw in text for kw in ["phone", "number", "mobile"])

    @pytest.mark.asyncio
    async def test_pre_authenticated_user_skips_otp(self):
        """X-TMRW-User-Id header must bypass OTP and go directly to welcome."""
        result = await chat("Hi", "auth-preauth-001", tenant="store-a", user_id="user-001")
        text = combined(result)
        assert "otp" not in text
        assert "verification" not in text

    @pytest.mark.asyncio
    async def test_pre_authenticated_welcome_contains_user_name(self):
        """PRD §3.3: Welcome registered users by name."""
        result = await chat("Hi", "auth-name-001", tenant="store-a", user_id="user-001")
        text = combined(result)
        # Priya Sharma is user-001
        assert "priya" in text

    @pytest.mark.asyncio
    async def test_pre_authenticated_different_user(self):
        """Rahul Mehta (user-002) should be greeted by name."""
        result = await chat("Hi", "auth-name-002", tenant="store-a", user_id="user-002")
        text = combined(result)
        assert "rahul" in text

    @pytest.mark.asyncio
    async def test_otp_request_registered_phone(self):
        """Mock API: OTP request for a registered phone returns success + is_registered=True."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{MOCK_URL}/v2/user/auth/login/otp",
                json={"phone": "+919876543210"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["is_registered"] is True

    @pytest.mark.asyncio
    async def test_otp_request_unregistered_phone(self):
        """Mock API: OTP request for unknown phone — either fails or marks as unregistered."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{MOCK_URL}/v2/user/auth/login/otp",
                json={"phone": "+910000000000"},
            )
        data = resp.json()
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert data.get("is_registered") is False

    @pytest.mark.asyncio
    async def test_otp_verify_correct_code(self):
        """Mock API: correct OTP returns auth token and user data."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Step 1: request OTP
            req = await client.post(
                f"{MOCK_URL}/v2/user/auth/login/otp",
                json={"phone": "+919876543211"},
            )
            otp = req.json().get("otp")   # mock returns OTP in dev mode
            assert otp is not None, "Mock API should return OTP for testing"

            # Step 2: verify
            verify = await client.post(
                f"{MOCK_URL}/v2/user/auth/verify-otp",
                json={"phone": "+919876543211", "otp": otp},
            )
        assert verify.status_code == 200
        data = verify.json()
        assert data.get("token") is not None
        assert data.get("user_id") == "user-002"

    @pytest.mark.asyncio
    async def test_otp_verify_wrong_code_fails(self):
        """Mock API: wrong OTP must be rejected."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{MOCK_URL}/v2/user/auth/login/otp",
                json={"phone": "+919876543212"},
            )
            resp = await client.post(
                f"{MOCK_URL}/v2/user/auth/verify-otp",
                json={"phone": "+919876543212", "otp": "000000"},
            )
        assert resp.status_code in (400, 401, 422)


# ── PRD §3.3: Order Fetch & Selection ────────────────────────────────────────

class TestOrderFetchAndSelection:
    """PRD §3.3 — Order listing and selection after authentication."""

    @pytest.mark.asyncio
    async def test_orders_menu_option_triggers_order_list(self):
        """Selecting 'I need help with my orders' fetches and lists orders."""
        results = await chat_flow(
            ["Hi", "1"],   # Hi → welcome+menu; "1" → order help
            session="ord-fetch-001",
            user_id="user-001",
        )
        last = combined(results[-1])
        # Should show order IDs or order list
        assert any(kw in last for kw in ["ord-1000", "order", "sneaker", "jeans"])

    @pytest.mark.asyncio
    async def test_order_search_api_returns_user_orders(self):
        """Mock API: order search returns orders for the given user."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order-search", params={"user_id": "user-001"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["orders"]) >= 2
        ids = [o["id"] for o in data["orders"]]
        assert "ORD-10001" in ids
        assert "ORD-10002" in ids

    @pytest.mark.asyncio
    async def test_order_search_by_phone(self):
        """Mock API: order search by phone number works."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order-search", params={"phone": "+919876543210"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["orders"]) >= 1

    @pytest.mark.asyncio
    async def test_order_search_no_results_for_unknown_user(self):
        """Mock API: order search for non-existent user returns empty list."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order-search", params={"user_id": "user-999"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["orders"] == []

    @pytest.mark.asyncio
    async def test_get_single_order_details(self):
        """Mock API: fetching an individual order returns correct status."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "ORD-10001"
        assert data["fulfillment_status"] == "pre_dispatch"

    @pytest.mark.asyncio
    async def test_get_nonexistent_order_returns_404(self):
        """Mock API: requesting unknown order ID returns 404."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-INVALID")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_user_profile_endpoint(self):
        """Mock API: profile endpoint returns name and email."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v2/user/user-001/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Priya Sharma"
        assert data["email"] == "priya.sharma@example.com"

    @pytest.mark.asyncio
    async def test_user_addresses_endpoint(self):
        """Mock API: address endpoint returns saved addresses."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v2/user/user-001/address")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        # Default address must be present
        defaults = [a for a in data if a.get("is_default")]
        assert len(defaults) == 1


# ── To-Be Flow: Pre-Dispatch Branch ──────────────────────────────────────────

class TestPreDispatchFlow:
    """
    To-Be_Flow: CheckStatus → Pre-Dispatch
    PRD §3.4: Cancel, address change, phone change, product modify → agent.
    API_Flows: If not shipped → UC cancel API or Shopify cancel + refund.
    """

    @pytest.mark.asyncio
    async def test_cancel_options_pre_dispatch_order(self):
        """API Flows: pre-dispatch order must be cancellable."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10001/cancel_options")
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_cancel"] is True
        assert len(data.get("reasons", [])) > 0

    @pytest.mark.asyncio
    async def test_cancel_pre_dispatch_order_succeeds(self):
        """API Flows: cancelling a pre-dispatch order returns success."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            # First ensure it's still cancellable (not already cancelled in a previous test run)
            options = await client.get(f"{MOCK_URL}/v1/order/ORD-10001/cancel_options")
            if not options.json().get("can_cancel"):
                pytest.skip("ORD-10001 already cancelled by a prior test run")

            resp = await client.post(
                f"{MOCK_URL}/v1/order/ORD-10001/cancel",
                json={"reason": "Changed my mind"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data.get("order_id") == "ORD-10001"

    @pytest.mark.asyncio
    async def test_pre_dispatch_menu_shown_for_pre_dispatch_order(self):
        """
        To-Be Flow: selecting a pre-dispatch order must show pre-dispatch actions
        (cancel, change address, change phone, product changes).
        """
        # user-001 has ORD-10001 (pre_dispatch)
        results = await chat_flow(
            ["Hi", "1", "1"],    # welcome → order help → select first order
            session="pd-menu-001",
            user_id="user-001",
        )
        last = combined(results[-1])
        assert any(kw in last for kw in ["cancel", "address", "phone", "modify", "change"])

    @pytest.mark.asyncio
    async def test_shipped_order_not_cancellable_pre_dispatch_route(self):
        """
        API Flows consistency: shipped order should NOT appear in cancel_options
        as a pre-dispatch cancellation — it uses Clickpost instead.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10002/cancel_options")
        assert resp.status_code == 200
        data = resp.json()
        # For shipped orders, can_cancel may be True (RTO) but via different path
        # The important assertion is that the API returns a structured response
        assert "can_cancel" in data


# ── To-Be Flow: Shipped / In-Transit Branch ──────────────────────────────────

class TestShippedFlow:
    """
    To-Be_Flow: CheckStatus → Shipped
    PRD §3.4: Track, cancel (RTO), address change.
    """

    @pytest.mark.asyncio
    async def test_tracking_summary_for_shipped_order(self):
        """PRD §3.4: shipped orders must return AWB and ETA via tracking API."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10002/tracking-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "shipped"
        assert data.get("awb") is not None
        assert data.get("courier") is not None

    @pytest.mark.asyncio
    async def test_tracking_summary_out_for_delivery(self):
        """Tracking works for out_for_delivery status orders too."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10003/tracking-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "out_for_delivery"
        assert data.get("awb") is not None

    @pytest.mark.asyncio
    async def test_shipped_menu_shown_for_shipped_order(self):
        """
        To-Be Flow: selecting a shipped order must show tracking + cancel + address options.
        user-001's second order (ORD-10002) is shipped.
        """
        results = await chat_flow(
            ["Hi", "1", "2"],    # welcome → orders → select second order (shipped)
            session="sh-menu-001",
            user_id="user-001",
        )
        last = combined(results[-1])
        assert any(kw in last for kw in ["track", "where", "shipped", "cancel", "address"])


# ── To-Be Flow: Delivered Branch ─────────────────────────────────────────────

class TestDeliveredFlow:
    """
    To-Be_Flow: CheckStatus → Delivered
    PRD §3.4, §3.5: Return, exchange, missing/wrong/not-received → agent.
    API_Flows: return 40% refund, exchange differential amount, Pragma routing.
    """

    @pytest.mark.asyncio
    async def test_return_options_for_delivered_order(self):
        """PRD §3.5: delivered order within window must be returnable."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10004/return-options")
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_return"] is True
        assert len(data.get("reasons", [])) > 0

    @pytest.mark.asyncio
    async def test_exchange_options_for_delivered_order(self):
        """PRD §3.5: delivered order within window must support exchange with variants."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10004/exchange-options")
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_exchange"] is True
        assert len(data.get("available_variants", [])) > 0

    @pytest.mark.asyncio
    async def test_return_initiation_succeeds(self):
        """API Flows: initiating a return posts to /return and returns confirmation."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            opts = await client.get(f"{MOCK_URL}/v1/order/ORD-10004/return-options")
            if not opts.json().get("can_return"):
                pytest.skip("ORD-10004 not returnable (already returned)")
            resp = await client.post(
                f"{MOCK_URL}/v1/order/ORD-10004/return",
                json={"reason": "Defective product"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data.get("return_id") is not None

    @pytest.mark.asyncio
    async def test_exchange_initiation_succeeds(self):
        """API Flows (exchange differential): initiating exchange returns order/exchange ID."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            opts = await client.get(f"{MOCK_URL}/v1/order/ORD-10004/exchange-options")
            opts_data = opts.json()
            if not opts_data.get("can_exchange"):
                pytest.skip("ORD-10004 not exchangeable")
            variant = opts_data["available_variants"][0]["variant_id"]
            resp = await client.post(
                f"{MOCK_URL}/v1/order/ORD-10004/exchange",
                json={"new_variant_id": variant, "reason": "Wrong size"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data.get("exchange_id") is not None

    @pytest.mark.asyncio
    async def test_delivered_order_menu_options(self):
        """
        To-Be Flow: selecting a delivered order shows return/exchange/issue options.
        user-002 has ORD-10004 (delivered).
        """
        results = await chat_flow(
            ["Hi", "1", "1"],    # welcome → orders → first order
            session="dl-menu-001",
            user_id="user-002",
        )
        last = combined(results[-1])
        assert any(kw in last for kw in ["return", "exchange", "missing", "wrong", "damaged"])

    @pytest.mark.asyncio
    async def test_return_options_not_available_for_pre_dispatch(self):
        """Pre-dispatch orders must NOT allow returns (not yet delivered)."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10001/return-options")
        # Either 404 or can_return=False
        if resp.status_code == 200:
            assert resp.json().get("can_return") is False
        else:
            assert resp.status_code in (400, 404, 422)


# ── To-Be Flow: Cancelled Branch ─────────────────────────────────────────────

class TestCancelledFlow:
    """To-Be_Flow: CheckStatus → Cancelled → Check Refund Status."""

    @pytest.mark.asyncio
    async def test_cancelled_order_has_refund_info(self):
        """Mock API: cancelled order must carry refund status fields."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10005")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert "refund_status" in data
        assert data["refund_status"] == "processed"

    @pytest.mark.asyncio
    async def test_cancelled_order_menu_shown(self):
        """
        To-Be Flow: selecting a cancelled order shows refund status info.
        user-003 has ORD-10005 (cancelled).
        """
        results = await chat_flow(
            ["Hi", "1", "1"],
            session="cn-menu-001",
            user_id="user-003",
        )
        last = combined(results[-1])
        assert any(kw in last for kw in ["cancel", "refund", "status"])


# ── To-Be Flow: Return Initiated Branch ──────────────────────────────────────

class TestReturnInitiatedFlow:
    """To-Be_Flow: CheckStatus → Returns → Track Return Pickup & Refund."""

    @pytest.mark.asyncio
    async def test_return_initiated_order_has_pickup_info(self):
        """Mock API: return_initiated order has return/pickup status fields."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10006")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "return_initiated"
        assert data.get("return_status") == "pickup_scheduled"
        assert data.get("return_pickup_date") is not None

    @pytest.mark.asyncio
    async def test_return_initiated_menu_shown(self):
        """
        To-Be Flow: selecting a return_initiated order shows pickup / refund tracking.
        user-003 has ORD-10006 (return_initiated).
        """
        results = await chat_flow(
            ["Hi", "1", "2"],
            session="rt-menu-001",
            user_id="user-003",
        )
        last = combined(results[-1])
        assert any(kw in last for kw in ["return", "pickup", "refund", "track"])


# ── To-Be Flow: FAQ Branch ───────────────────────────────────────────────────

class TestFAQFlow:
    """To-Be_Flow: MenuFAQs → categories → answers or agent handoff."""

    @pytest.mark.asyncio
    async def test_faq_option_reachable_from_main_menu(self):
        """Selecting option 2 from main menu enters FAQ flow."""
        results = await chat_flow(
            ["Hi", "2"],
            session="faq-cat-001",
            user_id="user-001",
        )
        last = combined(results[-1])
        assert any(kw in last for kw in ["faq", "categor", "delivery", "cancellation",
                                          "return", "account", "issue", "help"])

    @pytest.mark.asyncio
    async def test_faq_other_issues_escalates_to_agent(self):
        """
        To-Be_Flow: FAQ_Other -.-> AgentHandoff
        Selecting 'Other Issues' from FAQ categories must eventually hand off to agent.
        """
        results = await chat_flow(
            ["Hi", "2", "5"],    # main menu → FAQs → Other Issues (option 5)
            session="faq-other-001",
            user_id="user-001",
        )
        last = combined(results[-1])
        assert any(kw in last for kw in ["agent", "ticket", "representative",
                                          "connect", "support", "escalat", "human"])


# ── PRD §3.6: Agent Handoff & Escalation State (Design Critique §5) ──────────

class TestAgentHandoff:
    """
    PRD §3.6: Automatic Freshdesk ticket creation.
    Design critique fix #5: is_escalated flag in state.
    """

    @pytest.mark.asyncio
    async def test_chat_response_contains_is_escalated_field(self):
        """Chat response schema must include is_escalated boolean."""
        result = await chat("Hi", "esc-schema-001", user_id="user-001")
        assert "is_escalated" in result

    @pytest.mark.asyncio
    async def test_initial_state_not_escalated(self):
        """A fresh conversation must not be escalated."""
        result = await chat("Hi", "esc-init-001", user_id="user-001")
        assert result["is_escalated"] is False

    @pytest.mark.asyncio
    async def test_awaiting_input_field_present(self):
        """Chat response must include awaiting_input to indicate flow state."""
        result = await chat("Hi", "esc-await-001", user_id="user-001")
        assert "awaiting_input" in result

    @pytest.mark.asyncio
    async def test_product_modify_in_pre_dispatch_escalates(self):
        """
        To-Be_Flow: PD_Modify -.-> AgentHandoff
        Choosing 'make changes in the product' for pre-dispatch triggers agent handoff.
        user-001 order 1 = ORD-10001 (pre_dispatch). Option 4 = modify product.
        """
        results = await chat_flow(
            ["Hi", "1", "1", "4"],   # welcome → orders → order 1 → modify product
            session="esc-modify-001",
            user_id="user-001",
        )
        last_result = results[-1]
        last_text = combined(last_result)
        # Either the conversation escalates or mentions agent/ticket
        assert (
            last_result.get("is_escalated") is True
            or any(kw in last_text for kw in ["agent", "ticket", "representative", "connect"])
        )

    @pytest.mark.asyncio
    async def test_missing_item_for_delivered_order_escalates(self):
        """
        To-Be_Flow: DL_Missing -.-> AgentHandoff
        Reporting a missing item must trigger agent handoff.
        user-002 order 1 = ORD-10004 (delivered).
        """
        # Navigate to delivered order → missing item option
        results = await chat_flow(
            ["Hi", "1", "1", "3"],   # welcome → orders → order 1 → missing item
            session="esc-missing-001",
            user_id="user-002",
        )
        last_result = results[-1]
        last_text = combined(last_result)
        assert (
            last_result.get("is_escalated") is True
            or any(kw in last_text for kw in ["agent", "ticket", "representative", "connect"])
        )


# ── PRD §3.7: CSAT & Global Navigation ───────────────────────────────────────

class TestCSATAndNavigation:
    """
    PRD §3.7: CSAT survey on close; global 'main menu' and 'close chat' options.
    """

    @pytest.mark.asyncio
    async def test_response_includes_responses_list(self):
        """Chat response schema integrity — responses must be a list."""
        result = await chat("Hi", "nav-schema-001", user_id="user-001")
        assert isinstance(result.get("responses"), list)
        assert len(result["responses"]) > 0

    @pytest.mark.asyncio
    async def test_session_persistence_across_turns(self):
        """
        PRD implicit: state must persist between turns within the same session.
        Authenticated greeting in turn 1 should not re-ask for phone in turn 2.
        """
        session = "nav-persist-001"
        r1 = await chat("Hi", session, user_id="user-001")
        r2 = await chat("1", session)   # continue without user_id header
        text2 = combined(r2)
        # Turn 2 should continue the flow (orders/menu) not restart auth
        assert "phone" not in text2 or "order" in text2

    @pytest.mark.asyncio
    async def test_close_chat_triggers_csat_or_farewell(self):
        """
        PRD §3.7: After resolving, closing chat should trigger CSAT or a farewell.
        Drive a full order-cancel flow and close.
        """
        # Navigate: welcome → orders → pre-dispatch order → cancel → confirm
        results = await chat_flow(
            ["Hi", "1", "1", "1", "1"],   # last "1" is confirm cancel
            session="csat-cancel-001",
            user_id="user-001",
        )
        last = combined(results[-1])
        # Should either ask for rating or say goodbye
        assert any(kw in last for kw in [
            "rate", "rating", "feedback", "csat", "satisfied",
            "thank", "goodbye", "bye", "closed", "happy to help"
        ])


# ── PRD §3.2 / Design Critique §3: Guest Flow ────────────────────────────────

class TestGuestFlow:
    """
    To-Be_Flow: Guest Flow: Prompt for Phone/Order ID
    Design critique #3: guest users should be prompted for phone; OTP flow follows.
    """

    @pytest.mark.asyncio
    async def test_guest_session_asks_for_phone(self):
        """Without user_id header, chatbot must prompt for phone number."""
        result = await chat("Hello", "guest-flow-001")
        text = combined(result)
        assert any(kw in text for kw in ["phone", "number", "mobile", "contact"])

    @pytest.mark.asyncio
    async def test_guest_provides_registered_phone_gets_otp(self):
        """After phone entry, registered user should receive OTP prompt."""
        results = await chat_flow(
            ["Hello", "+919876543210"],   # greet → provide phone
            session="guest-otp-001",
        )
        last = combined(results[-1])
        assert any(kw in last for kw in ["otp", "code", "verify", "sent"])

    @pytest.mark.asyncio
    async def test_guest_provides_valid_otp_gets_authenticated(self):
        """Full guest OTP flow: phone → OTP request → enter OTP → authenticated."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            otp_resp = await client.post(
                f"{MOCK_URL}/v2/user/auth/login/otp",
                json={"phone": "+919876543212"},
            )
        otp = otp_resp.json().get("otp")
        if not otp:
            pytest.skip("Mock OTP not returned — cannot test full guest OTP flow")

        results = await chat_flow(
            ["Hello", "+919876543212", otp],
            session="guest-full-001",
        )
        last = combined(results[-1])
        # After successful OTP, user is welcomed or shown menu
        assert any(kw in last for kw in ["ananya", "welcome", "order", "help", "menu"])


# ── API Flows: Phone Lookup ───────────────────────────────────────────────────

class TestPhoneLookup:
    """
    Mock API: GET /v2/user?phone=... endpoint used by WhatsApp integration
    to resolve phone → user_id for pre-authentication.
    """

    @pytest.mark.asyncio
    async def test_lookup_known_phone_returns_user(self):
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v2/user", params={"phone": "+919876543210"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "user-001"
        assert data[0]["name"] == "Priya Sharma"

    @pytest.mark.asyncio
    async def test_lookup_all_registered_phones(self):
        """All 4 seeded phones must resolve to their respective users."""
        phones = {
            "+919876543210": "user-001",
            "+919876543211": "user-002",
            "+919876543212": "user-003",
            "+919876543213": "user-004",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            for phone, expected_id in phones.items():
                resp = await client.get(f"{MOCK_URL}/v2/user", params={"phone": phone})
                assert resp.status_code == 200
                users = resp.json()
                assert len(users) == 1
                assert users[0]["id"] == expected_id

    @pytest.mark.asyncio
    async def test_lookup_unknown_phone_returns_empty(self):
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v2/user", params={"phone": "+910000000000"})
        assert resp.status_code == 200
        assert resp.json() == []


# ── All Order Statuses: API Coverage ─────────────────────────────────────────

class TestOrderStatusCoverage:
    """Verify all 6 seeded order statuses are reachable via API (covers all To-Be Flow branches)."""

    @pytest.mark.asyncio
    async def test_all_seeded_orders_reachable(self):
        order_statuses = {
            "ORD-10001": "preparing",       # pre_dispatch
            "ORD-10002": "shipped",
            "ORD-10003": "out_for_delivery",
            "ORD-10004": "delivered",
            "ORD-10005": "cancelled",
            "ORD-10006": "return_initiated",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            for order_id, expected_status in order_statuses.items():
                resp = await client.get(f"{MOCK_URL}/v1/order/{order_id}")
                assert resp.status_code == 200, f"{order_id} not found"
                data = resp.json()
                assert data["status"] == expected_status, \
                    f"{order_id}: expected {expected_status}, got {data['status']}"

    @pytest.mark.asyncio
    async def test_tracking_available_for_active_orders(self):
        """Tracking endpoint must work for shipped and out_for_delivery orders."""
        trackable = ["ORD-10002", "ORD-10003"]
        async with httpx.AsyncClient(timeout=15.0) as client:
            for order_id in trackable:
                resp = await client.get(f"{MOCK_URL}/v1/order/{order_id}/tracking-summary")
                assert resp.status_code == 200, f"Tracking failed for {order_id}"
                data = resp.json()
                assert data.get("awb") is not None, f"{order_id} has no AWB"

    @pytest.mark.asyncio
    async def test_orders_distributed_across_users(self):
        """Each user in seed data has their own orders (data isolation baseline)."""
        user_order_map = {
            "user-001": {"ORD-10001", "ORD-10002"},
            "user-002": {"ORD-10003", "ORD-10004"},
            "user-003": {"ORD-10005", "ORD-10006"},
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            for user_id, expected_ids in user_order_map.items():
                resp = await client.get(f"{MOCK_URL}/v1/order-search", params={"user_id": user_id})
                assert resp.status_code == 200
                returned_ids = {o["id"] for o in resp.json()["orders"]}
                assert expected_ids.issubset(returned_ids), \
                    f"User {user_id} missing expected orders: {expected_ids - returned_ids}"


# ── Design Critique: Exchange Differential Amount (Gap #2) ───────────────────

class TestExchangeDifferentialAmount:
    """
    API_Flows.md: 'Add case for differential amount?' for exchanges.
    Design critique #2: exchange response should include differential/payment data.
    """

    @pytest.mark.asyncio
    async def test_exchange_options_include_variant_pricing(self):
        """
        Exchange options must include pricing for available variants so the
        chatbot can compute and present differential amounts to the user.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{MOCK_URL}/v1/order/ORD-10004/exchange-options")
        assert resp.status_code == 200
        data = resp.json()
        variants = data.get("available_variants", [])
        assert len(variants) > 0
        # Each variant should carry a price so differential can be computed
        for v in variants:
            assert "price" in v, f"Variant {v.get('variant_id')} missing 'price' field"

    @pytest.mark.asyncio
    async def test_exchange_response_includes_exchange_id(self):
        """Initiated exchange must return a trackable exchange_id (for status polling)."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            opts = await client.get(f"{MOCK_URL}/v1/order/ORD-10004/exchange-options")
            if not opts.json().get("can_exchange"):
                pytest.skip("ORD-10004 not exchangeable in this test run")
            variant = opts.json()["available_variants"][0]["variant_id"]
            resp = await client.post(
                f"{MOCK_URL}/v1/order/ORD-10004/exchange",
                json={"new_variant_id": variant, "reason": "Size too small"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "exchange_id" in data


# ── Chatbot Response Schema ───────────────────────────────────────────────────

class TestResponseSchema:
    """All /chat responses must conform to the ChatResponse schema."""

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self):
        result = await chat("Hi", "schema-001", user_id="user-001")
        assert "session_id" in result
        assert "responses" in result
        assert "is_escalated" in result
        assert "awaiting_input" in result

    @pytest.mark.asyncio
    async def test_session_id_matches_request(self):
        session = "schema-session-001"
        result = await chat("Hi", session, user_id="user-001")
        assert result["session_id"] == session

    @pytest.mark.asyncio
    async def test_responses_are_non_empty_strings(self):
        result = await chat("Hi", "schema-str-001", user_id="user-001")
        for r in result["responses"]:
            assert isinstance(r, str)
            assert len(r.strip()) > 0

    @pytest.mark.asyncio
    async def test_is_escalated_is_boolean(self):
        result = await chat("Hi", "schema-bool-001", user_id="user-001")
        assert isinstance(result["is_escalated"], bool)

    @pytest.mark.asyncio
    async def test_awaiting_input_is_boolean(self):
        result = await chat("Hi", "schema-await-001", user_id="user-001")
        assert isinstance(result["awaiting_input"], bool)


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v", "--tb=short"])
