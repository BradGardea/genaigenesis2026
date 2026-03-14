"""Forecasts service — coordinate and region-based weather forecasting.

Uses Open-Meteo (no API key required) for hourly and daily forecast data.
Region resolution uses a static lookup table to avoid external geocoding.
"""

from typing import Optional

import httpx

from app.providers import open_meteo, nhc
from app.schemas.forecast_models import (
    HourlyForecastItem,
    HourlyForecastResponse,
    DailyForecastItem,
    DailyForecastResponse,
    RegionForecastResponse,
    TropicalStormSummary,
    FloodRegionForecast,
)

# Static region name -> (lat, lon) lookup. Extend as needed.
KNOWN_REGIONS: dict[str, tuple[float, float]] = {
    "los angeles": (34.05, -118.25),
    "miami": (25.77, -80.19),
    "new orleans": (29.95, -90.07),
    "houston": (29.76, -95.37),
    "new york": (40.71, -74.01),
    "chicago": (41.85, -87.65),
    "phoenix": (33.45, -112.07),
    "seattle": (47.61, -122.33),
    "denver": (39.74, -104.98),
}


def _resolve_region(name: str) -> tuple[float, float] | None:
    """Resolve a region name to (lat, lon) using the static table."""
    return KNOWN_REGIONS.get(name.lower().strip())


async def get_hourly_forecast(lat: float, lon: float) -> HourlyForecastResponse:
    """Fetch and structure a 48-hour hourly forecast for a coordinate pair."""
    async with httpx.AsyncClient(timeout=20) as client:
        raw = await open_meteo.fetch_hourly_forecast(client, lat, lon)

    hourly_raw = raw.get("hourly", {})
    times = hourly_raw.get("time", [])
    temps = hourly_raw.get("temperature_2m", [])
    winds = hourly_raw.get("wind_speed_10m", [])
    precip_probs = hourly_raw.get("precipitation_probability", [])
    humidities = hourly_raw.get("relative_humidity_2m", [])

    items = [
        HourlyForecastItem(
            time=t,
            temperature_c=temps[i] if i < len(temps) else None,
            wind_speed_kmh=winds[i] if i < len(winds) else None,
            precipitation_probability=precip_probs[i] if i < len(precip_probs) else None,
            relative_humidity=humidities[i] if i < len(humidities) else None,
        )
        for i, t in enumerate(times[:48])
    ]

    return HourlyForecastResponse(
        latitude=raw.get("latitude", lat),
        longitude=raw.get("longitude", lon),
        timezone=raw.get("timezone", "UTC"),
        hourly=items,
    )


async def get_daily_forecast(lat: float, lon: float) -> DailyForecastResponse:
    """Fetch and structure a 7-day daily forecast for a coordinate pair."""
    async with httpx.AsyncClient(timeout=20) as client:
        raw = await open_meteo.fetch_daily_forecast(client, lat, lon)

    daily_raw = raw.get("daily", {})
    times = daily_raw.get("time", [])
    t_max = daily_raw.get("temperature_2m_max", [])
    t_min = daily_raw.get("temperature_2m_min", [])
    precip = daily_raw.get("precipitation_sum", [])
    wind_max = daily_raw.get("wind_speed_10m_max", [])

    items = [
        DailyForecastItem(
            date=d,
            temperature_max_c=t_max[i] if i < len(t_max) else None,
            temperature_min_c=t_min[i] if i < len(t_min) else None,
            precipitation_sum_mm=precip[i] if i < len(precip) else None,
            wind_speed_max_kmh=wind_max[i] if i < len(wind_max) else None,
        )
        for i, d in enumerate(times)
    ]

    return DailyForecastResponse(
        latitude=raw.get("latitude", lat),
        longitude=raw.get("longitude", lon),
        timezone=raw.get("timezone", "UTC"),
        daily=items,
    )


async def get_region_forecast(name: str) -> Optional[RegionForecastResponse]:
    """Fetch a daily forecast for a named region.

    Returns None if the region name is not in the static lookup table.
    """
    coords = _resolve_region(name)
    if not coords:
        return None
    lat, lon = coords
    daily = await get_daily_forecast(lat, lon)
    return RegionForecastResponse(
        region_name=name,
        latitude=lat,
        longitude=lon,
        note="Coordinates are approximate centroid for this region.",
        daily=daily.daily,
    )


async def get_active_tropical_storms() -> TropicalStormSummary:
    """Fetch active tropical storm summaries from the NHC CurrentStorms feed."""
    async with httpx.AsyncClient(timeout=20) as client:
        storms = await nhc.fetch_active_storms(client)
    return TropicalStormSummary(
        note=(
            "Data from NHC CurrentStorms feed. "
            "Structure varies by season; may be empty outside hurricane season."
        ),
        storms=storms,
    )


async def get_flood_region_forecast(name: str) -> FloodRegionForecast:
    """Return a flood-context placeholder for a named region.

    TODO: Integrate NOAA Water Services / USGS NWIS for gauge-based flood data.
    """
    return FloodRegionForecast(
        region_name=name,
        note=(
            "Flood region forecasting is a placeholder. "
            "Integrate NOAA Water Services (noaa_water.py) for site-specific streamflow data."
        ),
        alerts=[],
    )
