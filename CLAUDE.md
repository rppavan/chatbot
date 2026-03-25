# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in GOOGLE_API_KEY
```

Required `.env` variables:
```
GOOGLE_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite-preview
MOCK_API_BASE_URL=http://localhost:8100
SQLITE_DB_PATH=chatbot_memory.db
CHATBOT_PORT=8000

# WhatsApp integration (optional — only needed for whatsapp service)
WHATSAPP_VERIFY_TOKEN=...
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_PORT=8200
CHATBOT_BASE_URL=http://localhost:8000
```

## Running the Services

The mock API must run separately. The chatbot and integrations can run together or individually:

```bash
# Terminal 1 — mock e-commerce backend (port 8100)
python -m mock_api.app

# Terminal 2 — chatbot + all integrations in one process
python run.py

# Or run services individually:
# python -m src.main                      # chatbot only (port 8000)
# python -m integrations.whatsapp.app     # WhatsApp only (port 8200)
```

## Testing

Tests require both services to be running:

```bash
python -m pytest tests/ -v

# Run a single test
python -m pytest tests/test_integration.py::TestMockAPI::test_order_search -v
```

Sample manual test:
```bash
# Basic chat (session ID in header)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: store-a" \
  -H "X-TMRW-User-Session: test-001" \
  -d '{"message": "Hi"}'

# Pre-authenticated chat (skips OTP)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: store-a" \
  -H "X-TMRW-User-Session: test-002" \
  -H "X-TMRW-User-Id: user-001" \
  -d '{"message": "Hi"}'

# Phone-based user lookup
curl "http://localhost:8100/v2/user?phone=%2B919876543210"
```

## Architecture

### High-Level Data Flow

```
POST /chat (headers: X-Tenant-Id, X-TMRW-User-Session, X-TMRW-User-Id)
  → main.py: extract tenant + session from headers, build thread_id = "{tenant_id}:{session_id}"
  → if X-TMRW-User-Id present: fetch profile, set is_authenticated=True (skip OTP)
  → load snapshot from SQLite checkpoint (1-hour TTL invalidation)
  → if resuming interrupted flow: graph.ainvoke(Command(resume=user_message))
  → if fresh conversation: graph.ainvoke(initial_state)
  → extract AIMessage responses → return ChatResponse
```

### LangGraph State Machine (`src/graph/builder.py`)

The entire conversation is a **deterministic StateGraph** — no free-roaming agent. Every path is pre-defined with explicit nodes and conditional edges. The graph pauses at user input points via LangGraph's `interrupt()` and resumes on the next request via `Command(resume=...)`.

**Node organization by flow:**
- **Auth**: `check_user` → `guest_flow` (OTP) → `welcome`
- **Main menu**: `welcome` → `main_menu` → routes to Orders or FAQ
- **Orders**: `fetch_orders` → `show_orders` → branches by order status:
  - Pre-dispatch (preparing/ready): cancel, address change, phone change, modify product
  - Shipped: track, cancel (RTO), address change
  - Delivered: return, exchange, missing item, wrong/damaged, not received
  - Cancelled / return_initiated: informational only
- **FAQ**: `faq_categories` → `faq_answer` or `agent_handoff`
- **Terminal**: `csat_survey` → `close_chat` → END

### ConversationState (`src/state.py`)

A `TypedDict` with ~30 fields. Key groups:
- `messages` — chat history with `add_messages` reducer (appends, never overwrites)
- `tenant_id`, `tenant_config` — per-request tenant context
- `is_authenticated`, `auth_token`, `user_id`, `user_phone` — auth state
- `orders`, `selected_order`, `order_status` — order context
- `current_flow`, `awaiting_input`, `is_escalated`, `csat_collected` — navigation state

### Multi-Tenancy

Thread ID format `{tenant_id}:{session_id}` provides strict SQLite checkpoint isolation between tenants. Two pre-configured tenants exist in `src/config.py`: `store-a` and `store-b`. The `X-Tenant-Id` header selects the tenant; defaults to `store-a`.

### LLM Usage (`src/llm/`)

LLM is used only in two narrow places:
- **Intent classification** (`intent.py`): maps free-text input to known menu options. Temperature 0 (deterministic).
- **FAQ answering** (`faq.py`): generates answers from a hardcoded knowledge base (5 categories). Temperature 0.3. Falls back to `agent_handoff` if out-of-scope.

All other routing is rule-based (no LLM).

### Tools (`src/tools/`)

Thin async `httpx` wrappers — no business logic:
- `oms_tools.py` — order search, details, tracking, cancel/return/exchange options and actions
- `user_tools.py` — OTP request/verify, profile, addresses, phone lookup (`lookup_user_by_phone`)

### Mock API (`mock_api/`)

Mock e-commerce backend on port 8100 with in-memory data. Seed data in `mock_api/data.py` includes 3 users and 6 orders covering all statuses (pre-dispatch, shipped, out-for-delivery, delivered, cancelled, return_initiated). Use these for development and testing instead of a real OMS. Includes `GET /v2/user?phone=...` for phone-based user lookup.

### Integrations (`integrations/`)

Channel integrations live under `integrations/`, each as its own sub-package.

#### WhatsApp (`integrations/whatsapp/`)

Separate FastAPI service (port 8200) that bridges Meta WhatsApp Cloud API with the chatbot:
- **`GET /webhook`** — Meta webhook verification
- **`POST /webhook`** — Receives incoming WhatsApp messages, resolves phone → user_id via mock API, forwards to chatbot with pre-auth headers, sends response back via WhatsApp
- Session ID format: `whatsapp:{phone}` — ensures one conversation per phone number
- Requires `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, and `WHATSAPP_PHONE_NUMBER_ID` env vars
