# Repository Guidelines

## Project Structure & Module Organization
`src/` contains the chatbot service. Use [src/main.py](/Users/Apparao.Parwatikar/Desktop/tmrw/chatbot/src/main.py) for the FastAPI entry point, [src/graph/builder.py](/Users/Apparao.Parwatikar/Desktop/tmrw/chatbot/src/graph/builder.py) for LangGraph wiring, `src/nodes/` for flow steps, `src/tools/` for async API wrappers, and `src/llm/` for intent and FAQ LLM calls. `mock_api/` is the local e-commerce backend used in development and tests. `integrations/whatsapp/` contains the WhatsApp webhook bridge. `tests/` holds end-to-end and flow coverage; `docs/` stores product and design references.

## Build, Test, and Development Commands
Create the environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Run the mock backend with `python -m mock_api.app`. Run the chatbot only with `python -m src.main`, or start the chatbot plus integrations with `python run.py`. Execute the full test suite with `python -m pytest tests/ -v`. Run a focused check with `python -m pytest tests/test_integration.py::TestMockAPI::test_order_search -v`.

## Coding Style & Naming Conventions
Follow existing Python conventions: 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and explicit type hints where practical. Keep docstrings short and functional, matching the current codebase. Prefer small async helpers in `src/tools/` and keep business flow decisions inside graph nodes, not HTTP wrapper modules. No formatter or linter is configured in this repository, so keep changes PEP 8-aligned and consistent with nearby files.

## Testing Guidelines
Tests use `pytest`, `pytest-asyncio`, and `httpx`. Name files `test_*.py`, keep scenario-based names such as `test_pre_authenticated_flow`, and group related cases in `Test...` classes when it improves readability. Most tests expect the mock API on `:8100` and the chatbot on `:8000`; start both services before running the suite.

## Commit & Pull Request Guidelines
Recent history uses short subjects like `updates` and `Fixes + UAT`; prefer clearer imperative messages such as `fix shipped-order cancellation flow`. Keep each commit scoped to one change. Pull requests should summarize behavior changes, list test coverage run locally, note any `.env` or port requirements, and include sample request/response output when API behavior changes.

## Configuration & Data Notes
Base settings live in `.env` and [src/config.py](/Users/Apparao.Parwatikar/Desktop/tmrw/chatbot/src/config.py). Do not commit secrets. Treat `chatbot_memory.db` as local state, not source code, and avoid relying on checked-in database contents for tests.
