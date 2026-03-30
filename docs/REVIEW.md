# Code Review — 2026-03-29

Full multi-LLM review of entire codebase. AI-assisted provenance. All focus areas: correctness, security, architecture, TDD.

**Context:** The chatbot service sits behind an API gateway that handles user authentication and injects identity headers (`X-TMRW-User-Id`, `X-TMRW-User-Phone`). The WhatsApp integration service (port 8200) is a separate process called directly by Meta's servers and does NOT go through the API gateway.

---

## CRITICAL

### C-01 — OTP leaked to end users
**File:** `src/nodes/auth.py:104-108`
`debug_otp` from mock API response is appended directly to the user-facing message. Remove or gate behind `DEBUG_MODE=true` env var.

### C-02 — WhatsApp webhook has no signature verification
**File:** `integrations/whatsapp/app.py:123-162`
`X-Hub-Signature-256` HMAC header is never validated. The WhatsApp service is called directly by Meta's servers — it does **not** go through the API gateway — so the gateway provides zero protection here. Any attacker who discovers the webhook URL can spoof messages, impersonate users, or exhaust the access token. Validate the HMAC against the raw request body using your WhatsApp App Secret before processing any message.

### C-04 — Internal exceptions exposed to users
**Files:** `src/main.py:182-185`, `orders.py:46`, `shipped.py:77`, `delivered.py:91`, `pre_dispatch.py:131`
Raw `str(e)` returned in API responses. Log server-side, return a generic message to users.

### C-05 — TTL invalidation is a no-op
**File:** `src/main.py:118-121`
Sets `snapshot = None` but the SQLite checkpoint persists on disk. On the next request, `ainvoke` loads the stale checkpoint via the same `thread_id`. Must delete or expire the checkpoint, not just the local variable.

---

## Resolved by API gateway

| ID | Original Finding | Resolution |
|----|-----------------|------------|
| **C-03** | `X-TMRW-User-Phone` header trusts unauthenticated caller | **By design** — gateway authenticates user and injects this header. Internal callers (WhatsApp service → chatbot) are trusted. |
| **H-01** | No rate limiting | **Handled at gateway.** OTP brute force is still worth noting — confirm the gateway enforces per-session attempt limits on the OTP flow. |
| **H-06** | Unknown tenant silently falls back to `store-a` | **Low priority** — gateway should route/validate tenant. Still worth a defensive 400 at the service level, but not critical. |
| **H-02** | Phone number not validated in OTP guest flow | **N/A if gateway always provides identity.** If unauthenticated requests can reach the chatbot (to trigger the OTP flow), phone validation in `src/nodes/auth.py:44-52` is still needed. |

---

## HIGH

### H-03 — No timeout on httpx clients
**Files:** `src/tools/oms_tools.py`, `src/tools/user_tools.py` (all call sites)
`httpx.AsyncClient()` created without timeout. Upstream hang = indefinite block, cascading failure under load. Set `timeout=10.0` on all clients.

### H-04 — New httpx client per request
Same files as H-03. New TCP/TLS handshake on every tool call. Use a shared module-level client with connection pooling, closed in lifespan teardown.

### H-05 — `get_graph()` is dead code that leaks connections
**File:** `src/graph/builder.py:194-197`
Never called anywhere. Opens a SQLite connection that is never closed. Remove it.

### H-07 — Invalid order selection silently picks `orders[0]`
**File:** `src/nodes/orders.py:105-115`
User can unknowingly cancel the wrong order. Re-prompt instead of silently defaulting to first item.

### H-08 — CSAT rating not validated or stored
**File:** `src/nodes/common.py:28-32`
Any string accepted, no persistence. Validate 1–5, persist to a log or DB table.

---

## MEDIUM

### M-01 — Intent classification uses fragile substring match
**File:** `src/llm/intent.py:48-49`
`opt.lower() in response` can match unintended options (e.g., "back" matches anything containing "back"). Prefer exact match first.

### M-02 — Default routing fallback is a destructive action
`route_pre_dispatch` defaults to `pre_dispatch_cancel` on unknown input. Default should be re-prompt, never a destructive action.

### M-03 — Mock API uses `random.randint` for OTP
**File:** `mock_api/routes/auth.py:34,72`
Use `secrets.randbelow(9000) + 1000` to avoid setting an insecure pattern.

### M-04 — `aiosqlite` not in `requirements.txt`
**File:** `src/main.py:10`
Pulled in transitively today, fragile. Add `aiosqlite>=0.20.0` explicitly.

### M-05 — Mock API mutates global state during tests
`cancel_order` / `initiate_return` / `initiate_exchange` modify the global `ORDERS` dict in-place. Later tests silently skip due to stale state. Add a `/reset` endpoint and call it in a session-scoped fixture.

### M-06 — Conversation stuck after graph reaches END
Re-invoking the same thread_id after `close_chat → END` produces undefined behavior. Detect terminated graphs and start a fresh session or clear the checkpoint.

### M-07 — `interrupt()` wrapper silently truncates list resume values
**File:** `src/nodes/__init__.py:5-9`
Takes only `result[0]` silently. Log a warning or raise for unexpected list lengths > 1.

### M-08 — Zero unit tests
All three test files are E2E integration tests requiring live servers and LLM availability. Add `tests/unit/` for routing functions, node logic, and tool wrappers (mockable, fast, no external deps).

### M-09 — FAQ "can't answer" detection is fragile phrase matching
**File:** `src/nodes/faq.py:91`
Depends on LLM generating specific strings. Use structured output (`{"can_answer": bool, "answer": str}`) instead.

### M-10 — WhatsApp phone normalization inconsistency
**File:** `integrations/whatsapp/app.py:144-160`
Session ID uses normalized phone (`+91...`), reply sent to raw phone (`91...`). Normalize consistently.

---

## LOW

| ID | File | Issue |
|----|------|-------|
| L-01 | `src/llm/intent.py`, `faq.py` | LLM instantiated on every call — use singleton or `lru_cache` |
| L-02 | `src/llm/intent.py:14` | Intent classifier uses `temperature=0.3` but docs say 0 — non-deterministic routing |
| L-03 | `src/nodes/welcome.py:64-65` | Emoji digit matching only in welcome; missing in other routing nodes |
| L-04 | `mock_api/routes/users.py:78` | `if False` dead code block in `update_profile` |
| L-05 | `src/main.py` | No CORS middleware — if any web frontend calls this directly, requests will be blocked |
| L-06 | `src/main.py:6` | Unused `asyncio` import |
| L-07 | `src/main.py:40` | Startup uses `print()`, errors use `logging` — inconsistent |
| L-08 | `tests/test_flows.py:183` | `req.json().get("otp")` should be `"debug_otp"` — always returns None, causes silent test skips |
| L-09 | `src/config.py:42-48` | Unknown tenant silently falls back to `store-a` — add a defensive 400 even if gateway validates upstream |

---

## Summary

| Severity | Count | Notes |
|----------|-------|-------|
| Critical | 4 | Down from 5 — C-03 resolved by gateway design |
| High | 5 | Down from 8 — H-01, H-02, H-06 resolved/downgraded |
| Medium | 10 | Unchanged |
| Low | 9 | H-06 moved here as L-09 |

**Top priorities:**
1. **C-02** — WhatsApp webhook HMAC (bypasses gateway entirely — no protection today)
2. **C-01** — Remove OTP from user-facing messages
3. **C-05** — Fix broken TTL invalidation (stale graph state after 1 hour)
4. **C-04** — Strip exception details from user-facing error responses
5. **H-03/H-04** — Add timeouts + shared httpx client before production load
