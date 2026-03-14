"""Open-Meteo weather forecast provider.

No API key required. Provides hourly and daily forecast data for any
coordinate pair worldwide via the Open-Meteo public API.
"""

import httpx

from app.core.constants import OPEN_METEO_FORECAST_URL

# Variables requested for hourly forecasts
HOURLY_VARIABLES = (
    "temperature_2m,wind_speed_10m,precipitation_probability,relative_humidity_2m"
)

# Variables requested for daily forecasts
DAILY_VARIABLES = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
)


async def fetch_hourly_forecast(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    forecast_days: int = 2,
) -> dict:
    """Fetch hourly forecast data from Open-Meteo.

    Returns the raw API response dict, or an empty dict on any error.
    The `hourly` key contains parallel arrays indexed by time slot.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": HOURLY_VARIABLES,
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }
    try:
        r = await client.get(OPEN_METEO_FORECAST_URL, params=params)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


async def fetch_daily_forecast(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    forecast_days: int = 7,
) -> dict:
    """Fetch daily forecast data from Open-Meteo.

    Returns the raw API response dict, or an empty dict on any error.
    The `daily` key contains parallel arrays indexed by date.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": DAILY_VARIABLES,
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }
    try:
        r = await client.get(OPEN_METEO_FORECAST_URL, params=params)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}
