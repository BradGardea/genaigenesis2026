"""Events service — per-source event retrieval.

Provides drill-down access to individual provider data, complementing
the merged feed in alerts_service. Used by the /events/* endpoint group.
"""

from typing import List

import httpx

from app.providers import usgs, nasa_firms, noaa_alerts, gdacs
from app.schemas.alert_models import AlertSignal
from app.utils.normalization import (
    normalize_seismic,
    normalize_fires,
    normalize_weather_alerts,
    normalize_gdacs,
)
from app.core.env import NASA_FIRMS_KEY


async def fetch_seismic_events(limit: int = 10) -> List[AlertSignal]:
    """Return normalized seismic events from USGS."""
    async with httpx.AsyncClient(timeout=20) as client:
        raw = await usgs.fetch_raw_seismic(client, limit=limit)
    return normalize_seismic(raw)


async def fetch_fire_events(limit: int = 10) -> List[AlertSignal]:
    """Return normalized fire detections from NASA FIRMS."""
    async with httpx.AsyncClient(timeout=20) as client:
        raw = await nasa_firms.fetch_raw_fires(
            client, api_key=NASA_FIRMS_KEY or "", limit=limit
        )
    return normalize_fires(raw)


async def fetch_weather_events(limit: int = 10) -> List[AlertSignal]:
    """Return normalized active weather alerts from NOAA NWS."""
    async with httpx.AsyncClient(timeout=20) as client:
        raw = await noaa_alerts.fetch_raw_alerts(client, limit=limit)
    return normalize_weather_alerts(raw)


async def fetch_gdacs_events(limit: int = 10) -> List[AlertSignal]:
    """Return normalized global disaster events from GDACS."""
    async with httpx.AsyncClient(timeout=20) as client:
        raw = await gdacs.fetch_raw_events(client, limit=limit)
    return normalize_gdacs(raw)
