"""Forecast endpoints — coordinate and region-based weather forecasts."""

from fastapi import APIRouter, HTTPException, Query

from app.schemas.forecast_models import (
    HourlyForecastResponse,
    DailyForecastResponse,
    RegionForecastResponse,
    TropicalStormSummary,
    FloodRegionForecast,
)
from app.services import forecasts_service

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("/hourly", response_model=HourlyForecastResponse)
async def hourly_forecast(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
) -> HourlyForecastResponse:
    """Hourly weather forecast for a coordinate (48-hour window via Open-Meteo)."""
    return await forecasts_service.get_hourly_forecast(lat, lon)


@router.get("/daily", response_model=DailyForecastResponse)
async def daily_forecast(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
) -> DailyForecastResponse:
    """7-day daily weather forecast for a coordinate (via Open-Meteo)."""
    return await forecasts_service.get_daily_forecast(lat, lon)


@router.get("/region", response_model=RegionForecastResponse)
async def region_forecast(
    name: str = Query(
        ...,
        description="Region name (e.g. 'Los Angeles', 'Miami', 'Houston')",
    ),
) -> RegionForecastResponse:
    """Daily forecast for a named region using a static coordinate lookup.

    Supported regions: los angeles, miami, new orleans, houston, new york,
    chicago, phoenix, seattle, denver.
    """
    result = await forecasts_service.get_region_forecast(name)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Region '{name}' not recognized. "
                "Supported: los angeles, miami, new orleans, houston, new york, "
                "chicago, phoenix, seattle, denver."
            ),
        )
    return result


@router.get("/tropical/active", response_model=TropicalStormSummary)
async def active_tropical_storms() -> TropicalStormSummary:
    """Active tropical storm summaries from the National Hurricane Center."""
    return await forecasts_service.get_active_tropical_storms()


@router.get("/flood/region", response_model=FloodRegionForecast)
async def flood_region_forecast(
    name: str = Query(..., description="Region name"),
) -> FloodRegionForecast:
    """Flood forecast context for a named region.

    Currently a placeholder — returns a note directing integration of
    NOAA Water Services for real streamflow data.
    """
    return await forecasts_service.get_flood_region_forecast(name)
