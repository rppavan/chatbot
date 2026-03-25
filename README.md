# E-commerce CX Chatbot

Multi-tenant customer support chatbot for e-commerce platforms, built with **Python**, **LangChain**, **LangGraph**, and **SQLite**.

## Architecture

- **LangGraph StateGraph**: Deterministic guided flows for order tracking, cancellation, returns, exchanges
- **LangChain**: LLM orchestration for intent classification and FAQ answering
- **SQLite**: Chat memory persistence via LangGraph checkpointing
- **FastAPI**: REST API for chat interactions

## Quick Start

### 1. Setup Environment

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env  # Edit with your OPENAI_API_KEY
```

### 2. Start the Mock API Server

```bash
python -m mock_api.app
# Runs on http://localhost:8100
```

### 3. Start the Chatbot Server

```bash
# In a separate terminal
source .venv/bin/activate
python -m src.main
# Runs on http://localhost:8000
```

### 4. Chat with the Bot

```bash
# Start a conversation
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: store-a" \
  -d '{"message": "Hi", "session_id": "my-session-001"}'

# Continue the conversation (same session_id)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: store-a" \
  -d '{"message": "+919876543210", "session_id": "my-session-001"}'
```

## Project Structure

```
chatbot/
├── src/                    # Chatbot application
│   ├── main.py             # FastAPI entry point (POST /chat)
│   ├── config.py           # Settings & tenant config
│   ├── state.py            # ConversationState TypedDict
│   ├── graph/builder.py    # LangGraph StateGraph construction
│   ├── nodes/              # Guided flow nodes
│   │   ├── auth.py         # Authentication & OTP
│   │   ├── welcome.py      # Welcome & main menu
│   │   ├── orders.py       # Order fetch, selection, routing
│   │   ├── pre_dispatch.py # Pre-dispatch actions (cancel, modify)
│   │   ├── shipped.py      # Shipped actions (track, cancel)
│   │   ├── delivered.py    # Post-delivery (return, exchange)
│   │   ├── faq.py          # FAQ categories & answers
│   │   ├── handoff.py      # Agent handoff (stubbed)
│   │   └── common.py       # CSAT & close chat
│   ├── tools/              # API client wrappers
│   │   ├── oms_tools.py    # Order management
│   │   ├── user_tools.py   # User auth & profile
│   │   └── tracking_tools.py
│   └── llm/                # LLM integration
│       ├── intent.py       # Intent classification
│       └── faq.py          # FAQ answer generation
├── mock_api/               # Mock API service
│   ├── app.py              # FastAPI server (port 8100)
│   ├── data.py             # Seed data
│   └── routes/             # API route handlers
├── tests/                  # Integration tests
├── docs/                   # Design documents
└── requirements.txt
```

## Running Tests

```bash
# Start both servers first (in separate terminals)
python -m mock_api.app
python -m src.main

# Run tests
python -m pytest tests/ -v
```

## Supported Flows

| Flow | Description |
|------|-------------|
| **Auth** | OTP-based login for registered users |
| **Order Tracking** | AWB, courier, ETA, tracking events |
| **Cancellation** | Pre-dispatch & shipped order cancellation with refund info |
| **Returns** | Eligibility check, reason selection, pickup scheduling |
| **Exchanges** | Variant selection with differential amount handling |
| **FAQ** | LLM-powered answers across 5 categories |
| **Agent Handoff** | Stubbed ticket creation for complex issues |
| **CSAT** | Post-interaction rating collection |

## Multi-Tenancy

Tenant isolation is achieved via:
- `X-Tenant-Id` request header
- Thread ID format: `{tenant_id}:{session_id}` for state persistence
- Tenant-scoped API configuration
