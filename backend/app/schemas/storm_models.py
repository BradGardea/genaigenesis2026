"""Pydantic response models for tropical storm endpoints.

These models are intentionally separate from forecast_models.py so that
storm geometry (eye, cone, wind radii) never leaks into point-based
weather or hazard prediction schemas.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class StormWindRadii(BaseModel):
    """Wind radii for a single wind-speed threshold at the current storm position."""

    wind_speed_kt: int = Field(
        ..., description="Wind-speed threshold in knots (typically 34, 50, or 64)"
    )
    ne_km: Optional[float] = Field(None, description="Northeast quadrant extent in km")
    se_km: Optional[float] = Field(None, description="Southeast quadrant extent in km")
    sw_km: Optional[float] = Field(None, description="Southwest quadrant extent in km")
    nw_km: Optional[float] = Field(None, description="Northwest quadrant extent in km")


class StormForecastPoint(BaseModel):
    """A single point on the official 5-day forecast track."""

    valid_time: str = Field(..., description="ISO 8601 forecast valid time (UTC)")
    latitude: float
    longitude: float
    max_wind_kt: Optional[int] = Field(
        None, description="Max sustained wind speed in knots at this forecast point"
    )
    min_pressure_mb: Optional[float] = Field(
        None, description="Minimum central pressure in mb at this forecast point"
    )
    classification: Optional[str] = Field(
        None,
        description="Storm classification at this forecast point (TD, TS, HU, TY, etc.)",
    )
    wind_radii: List[StormWindRadii] = Field(
        default_factory=list,
        description="34/50/64-kt wind radii at this forecast point, if provided",
    )


class ActiveStormItem(BaseModel):
    """Compact summary of one active tropical storm, suitable for list and map layers."""

    storm_id: str = Field(
        ..., description="Unique storm identifier, e.g. al012025 or ep022025"
    )
    name: str = Field(..., description="Storm name or INVEST designation")
    basin: str = Field(
        ...,
        description=(
            "Basin code: al (Atlantic), ep (East Pacific), "
            "cp (Central Pacific), wp (West Pacific), io (Indian Ocean), sh (Southern Hemisphere)"
        ),
    )
    classification: str = Field(
        ...,
        description="Current storm type classification: TD, TS, HU, TY, STY, TC, etc.",
    )
    intensity_kt: Optional[int] = Field(
        None, description="Maximum sustained wind speed in knots"
    )
    pressure_mb: Optional[float] = Field(
        None, description="Minimum central pressure in millibars"
    )
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    movement_dir_deg: Optional[int] = Field(
        None,
        description="Storm movement direction in degrees (0=N, 90=E, 180=S, 270=W)",
    )
    movement_speed_kt: Optional[float] = Field(
        None, description="Storm movement speed in knots"
    )
    last_update: Optional[str] = Field(
        None, description="ISO 8601 timestamp of the most recent advisory"
    )
    headline: Optional[str] = Field(None, description="Current public advisory headline")
    source: str = Field(default="nhc", description="Data provider identifier: nhc or jtwc")


class ActiveStormsResponse(BaseModel):
    """Response envelope for the active storms list endpoint."""

    storms: List[ActiveStormItem]
    count: int = Field(..., description="Total number of active storms returned")
    fetched_at: str = Field(
        ..., description="ISO 8601 UTC timestamp when this data was fetched"
    )
    note: Optional[str] = None


class StormDetail(BaseModel):
    """Full record for a single active tropical storm, including advisory links."""

    storm_id: str
    name: str
    basin: str
    classification: str
    intensity_kt: Optional[int] = None
    pressure_mb: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    movement_dir_deg: Optional[int] = None
    movement_speed_kt: Optional[float] = None
    last_update: Optional[str] = None
    headline: Optional[str] = None
    source: str = "nhc"
    public_advisory_url: Optional[str] = Field(
        None, description="URL to the latest public advisory text"
    )
    forecast_advisory_url: Optional[str] = Field(
        None, description="URL to the latest forecast/advisory discussion"
    )
    current_wind_radii: List[StormWindRadii] = Field(
        default_factory=list,
        description="Current 34/50/64-kt wind radii quadrants, if available from provider",
    )


class StormTrackPoint(BaseModel):
    """One observed or best-track position in a storm's history."""

    time: str = Field(
        ..., description="ISO 8601 observation or best-track time (UTC)"
    )
    latitude: float
    longitude: float
    max_wind_kt: Optional[int] = None
    min_pressure_mb: Optional[float] = None
    classification: Optional[str] = Field(
        None, description="Storm classification at this historical point"
    )


class StormTrackResponse(BaseModel):
    """Best-track or observed track data for a storm."""

    storm_id: str
    name: str
    source: str = Field(
        ..., description="Track data source identifier: nhc, jtwc, or ibtracs"
    )
    track: List[StormTrackPoint]
    note: Optional[str] = None


class StormGeometrySnapshot(BaseModel):
    """Point-in-time storm geometry: current center and wind-radii rings."""

    storm_id: str
    name: str
    valid_time: str = Field(
        ..., description="Validity time of this snapshot (ISO 8601 UTC)"
    )
    center_latitude: float
    center_longitude: float
    wind_radii: List[StormWindRadii] = Field(
        default_factory=list,
        description="34/50/64-kt wind radii for each quadrant at this valid time",
    )
    cone_geojson: Optional[dict] = Field(
        None,
        description=(
            "GeoJSON FeatureCollection for the 5-day forecast cone. "
            "Null when the provider advisory GeoJSON is unavailable."
        ),
    )
    source: str = "nhc"
    note: Optional[str] = None


class StormForecastResponse(BaseModel):
    """5-day forecast track and intensity guidance for a storm."""

    storm_id: str
    name: str
    source: str
    forecast_points: List[StormForecastPoint] = Field(
        default_factory=list,
        description="Ordered list of forecast positions and intensity values",
    )
    cone_geojson: Optional[dict] = Field(
        None,
        description="GeoJSON cone of uncertainty polygon for the full forecast period",
    )
    note: Optional[str] = None
