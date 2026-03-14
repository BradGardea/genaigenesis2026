"""Events endpoints — per-source event drill-down.

Provides source-specific access to disaster event data, complementing
the merged /alerts/signals feed. Useful for filtering and inspecting
individual provider feeds without the unified aggregation.
"""

from fastapi import APIRouter

from app.schemas.alert_models import AlertSignal
from app.services import events_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/seismic", response_model=list[AlertSignal])
async def seismic_events() -> list[AlertSignal]:
    """Recent seismic events from USGS (up to 10 from the hourly feed)."""
    return await events_service.fetch_seismic_events()


@router.get("/fires", response_model=list[AlertSignal])
async def fire_events() -> list[AlertSignal]:
    """Active fire detections from NASA FIRMS.

    Returns an empty list if NASA_FIRMS_KEY is not configured.
    """
    return await events_service.fetch_fire_events()


@router.get("/weather", response_model=list[AlertSignal])
async def weather_events() -> list[AlertSignal]:
    """Active weather alerts from NOAA NWS (up to 10)."""
    return await events_service.fetch_weather_events()


@router.get("/gdacs", response_model=list[AlertSignal])
async def gdacs_events() -> list[AlertSignal]:
    """Global disaster events from GDACS (up to 10)."""
    return await events_service.fetch_gdacs_events()
