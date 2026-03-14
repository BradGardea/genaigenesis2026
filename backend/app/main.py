from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version=settings.app_version)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


class AllowWSMiddleware(BaseHTTPMiddleware):
    """Skip CORS checks for WebSocket upgrade requests."""
    async def dispatch(self, request: Request, call_next):
        if request.headers.get("upgrade", "").lower() == "websocket":
            # Remove origin header so CORSMiddleware doesn't reject it
            headers = dict(request.scope["headers"])
            headers.pop(b"origin", None)
            request.scope["headers"] = list(headers.items())
        return await call_next(request)


# LIFO order: AllowWSMiddleware runs first, then CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AllowWSMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f">> {request.method} {request.url} | Origin: {request.headers.get('origin')}")
    return await call_next(request)


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }