from fastapi import APIRouter

from app.api.v1.endpoints import (
    alerts,
    city_state_steps,
    events,
    forecasts,
    health,
    information,
    hazards,
    realtime,
    routes,
    storms,
    weather_steps,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(alerts.router)
api_router.include_router(events.router)
api_router.include_router(forecasts.router)
api_router.include_router(routes.router)
api_router.include_router(hazards.router)
api_router.include_router(information.router)
api_router.include_router(realtime.router)
api_router.include_router(storms.router)
api_router.include_router(weather_steps.router)
api_router.include_router(city_state_steps.router)
