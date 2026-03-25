"""
Mock API Service — FastAPI application.
Serves mock e-commerce endpoints for chatbot testing.
Run: python -m mock_api.app
"""
import uvicorn
from fastapi import FastAPI

from mock_api.routes import auth, users, orders

app = FastAPI(
    title="E-commerce Mock API",
    description="Mock API service for chatbot integration testing",
    version="1.0.0",
)

# Register route modules
app.include_router(auth.router, tags=["Auth"])
app.include_router(users.router, tags=["Users"])
app.include_router(orders.router, tags=["Orders"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-api"}


if __name__ == "__main__":
    uvicorn.run("mock_api.app:app", host="0.0.0.0", port=8100, reload=True)
