from fastapi import APIRouter

from app.api.v1.endpoints import alerts, events, health, routes

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(alerts.router)
api_router.include_router(events.router)
api_router.include_router(routes.router)

