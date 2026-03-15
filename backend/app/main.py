from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version=settings.app_version)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


class AllowWSMiddleware:
    """Raw ASGI middleware — skip CORS for WebSocket upgrades.

    Using raw ASGI instead of BaseHTTPMiddleware to avoid buffering
    StreamingResponse / SSE streams.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            # Strip origin header so CORSMiddleware doesn't reject it
            scope["headers"] = [
                (k, v) for k, v in scope.get("headers", []) if k != b"origin"
            ]
        await self.app(scope, receive, send)


# LIFO order: AllowWSMiddleware runs first, then CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AllowWSMiddleware)


class LogRequestsMiddleware:
    """Raw ASGI middleware for request logging — avoids BaseHTTPMiddleware SSE buffering."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and "/stream" not in scope.get("path", ""):
            headers = dict(scope.get("headers", []))
            origin = headers.get(b"origin", b"").decode()
            print(f">> {scope['method']} {scope['path']} | Origin: {origin}")
        await self.app(scope, receive, send)


app.add_middleware(LogRequestsMiddleware)


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
