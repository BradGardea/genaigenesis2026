"""Alerts aggregation service.

Fetches and normalizes signals from all active disaster data providers
into a unified AlertSignal list. This is the primary data layer for
the /alerts/* endpoint group.
"""

import asyncio
from typing import List, Optional

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


async def fetch_all_signals() -> List[AlertSignal]:
    """Fetch and normalize signals from all configured providers in parallel.

    Individual provider failures are suppressed; partial results are returned
    so a single upstream outage does not take down the whole feed.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        results = await asyncio.gather(
            usgs.fetch_raw_seismic(client, limit=5),
            nasa_firms.fetch_raw_fires(client, api_key=NASA_FIRMS_KEY or "", limit=5),
            noaa_alerts.fetch_raw_alerts(client, limit=5),
            gdacs.fetch_raw_events(client, limit=5),
            return_exceptions=True,
        )

    seismic_raw, fires_raw, weather_raw, gdacs_raw = [
        r if isinstance(r, list) else [] for r in results
    ]

    signals: List[AlertSignal] = []
    signals.extend(normalize_seismic(seismic_raw))
    signals.extend(normalize_fires(fires_raw))
    signals.extend(normalize_weather_alerts(weather_raw))
    signals.extend(normalize_gdacs(gdacs_raw))
    return signals


async def fetch_signals_by_source(source: str) -> List[AlertSignal]:
    """Return signals filtered to a single named source.

    Known sources: usgs, nasa-firms, noaa-nws, gdacs.
    """
    all_signals = await fetch_all_signals()
    return [s for s in all_signals if s.source == source]


async def get_signal_by_id(signal_id: str) -> Optional[AlertSignal]:
    """Find a single signal by its ID across all providers, or return None."""
    all_signals = await fetch_all_signals()
    for s in all_signals:
        if s.id == signal_id:
            return s
    return None
