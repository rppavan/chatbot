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

# WhatsApp integration (optional — only needed when receiving WhatsApp messages)
WHATSAPP_VERIFY_TOKEN=...
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
```

## Running the Services

The mock API must run separately. The chatbot (including the WhatsApp webhook) runs as a single service:

```bash
# Terminal 1 — mock e-commerce backend (port 8100)
python -m mock_api.app

# Terminal 2 — unified chatbot service (port 8000)
python run.py

# Or directly:
python -m src.main
```

## API Endpoints

All endpoints are served on `CHATBOT_PORT` (default 8000):

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Main chat endpoint |
| `GET`  | `/webhook/whatsapp` | Meta webhook verification |
| `POST` | `/webhook/whatsapp` | Incoming WhatsApp messages |
| `GET`  | `/health` | Health check |

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

# Pre-authenticated chat (skips OTP — simulates API gateway injecting identity)
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

### Deployment Model

The service is designed to run behind an **API gateway** that handles authentication. The gateway injects user identity into headers before requests reach this service:
- `X-TMRW-User-Id` — authenticated user ID (skips OTP flow)
- `X-TMRW-User-Phone` — authenticated phone number (skips OTP flow)
- `X-Tenant-Id` — tenant routing

The WhatsApp webhook (`POST /whatsapp/webhook`) is also behind the API gateway. Meta webhook calls must be routed through the gateway to this endpoint.

### High-Level Data Flow

```
POST /chat (headers: X-Tenant-Id, X-TMRW-User-Session, X-TMRW-User-Id)
  → main.py: extract headers → call process_chat() in chat_handler.py
  → chat_handler.py: build thread_id = "{tenant_id}:{session_id}"
  → if X-TMRW-User-Id present: fetch profile, set is_authenticated=True (skip OTP)
  → load snapshot from SQLite checkpoint (1-hour TTL invalidation)
  → if resuming interrupted flow: graph.ainvoke(Command(resume=user_message))
  → if fresh conversation: graph.ainvoke(initial_state)
  → extract AIMessage responses → return ChatResponse

POST /whatsapp/webhook
  → whatsapp/router.py: verify HMAC signature → parse Meta payload
  → resolve phone → user_id via OMS API
  → call process_chat() directly (no HTTP hop) → send responses via WhatsApp Cloud API
```

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `src/main.py` | FastAPI app, lifespan, `/chat` endpoint, router mounting |
| `src/chat_handler.py` | Graph reference, `process_chat()` — shared by all channels |
| `src/graph/builder.py` | LangGraph StateGraph definition |
| `src/state.py` | `ConversationState` TypedDict |
| `src/config.py` | All environment-backed configuration |
| `integrations/whatsapp/router.py` | WhatsApp APIRouter — webhook routes, Meta API calls |

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

Channel integrations live under `integrations/`, each as its own sub-package, exported as FastAPI `APIRouter` instances and mounted in `src/main.py`.

#### WhatsApp (`integrations/whatsapp/router.py`)

Mounted at `/whatsapp`. Bridges Meta WhatsApp Cloud API with the chatbot:
- **`GET /webhook/whatsapp`** — Meta webhook verification
- **`POST /webhook/whatsapp`** — Receives incoming messages, validates `X-Hub-Signature-256` HMAC, resolves phone → user_id, calls `process_chat()` directly, sends response via WhatsApp Cloud API
- Session ID format: `whatsapp:{phone}` — ensures one conversation per phone number
- Requires `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, and `WHATSAPP_PHONE_NUMBER_ID` env vars
