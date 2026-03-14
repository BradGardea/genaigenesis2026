"""Pydantic models for weather forecast endpoint responses."""

from typing import List, Optional
from pydantic import BaseModel


class HourlyForecastItem(BaseModel):
    """A single hour of forecast data."""

    time: str
    temperature_c: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    precipitation_probability: Optional[int] = None
    relative_humidity: Optional[int] = None


class HourlyForecastResponse(BaseModel):
    """48-hour hourly forecast for a coordinate pair."""

    latitude: float
    longitude: float
    timezone: str
    hourly: List[HourlyForecastItem]


class DailyForecastItem(BaseModel):
    """A single day of forecast data."""

    date: str
    temperature_max_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    precipitation_sum_mm: Optional[float] = None
    wind_speed_max_kmh: Optional[float] = None


class DailyForecastResponse(BaseModel):
    """7-day daily forecast for a coordinate pair."""

    latitude: float
    longitude: float
    timezone: str
    daily: List[DailyForecastItem]


class RegionForecastResponse(BaseModel):
    """Daily forecast resolved from a named region."""

    region_name: str
    latitude: float
    longitude: float
    note: str
    daily: List[DailyForecastItem]


class TropicalStormSummary(BaseModel):
    """Active tropical storm summaries from NHC."""

    source: str = "nhc"
    note: str
    storms: List[dict] = []


class FloodRegionForecast(BaseModel):
    """Flood forecast context for a named region (placeholder)."""

    region_name: str
    note: str
    alerts: List[str] = []
