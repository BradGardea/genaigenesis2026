from pydantic import BaseModel, Field


class ThreatProximity(BaseModel):
    event_id: str
    event_title: str
    distance_km: float = Field(ge=0.0)
    bearing: str = Field(description="Cardinal direction from user to threat (N, NE, E, etc.)")
    hazard_velocity_kmh: float = Field(ge=0.0)
    hazard_direction: str = Field(description="Direction the hazard is moving (N, NE, E, etc.)")
    estimated_arrival_minutes: float | None = Field(
        None, description="Minutes until hazard reaches user; None if receding"
    )
    threat_level: str = Field(description="immediate | approaching | stable | receding")
    summary: str = Field(description="Voice-ready sentence for ASR")


class LoadSnapshot(BaseModel):
    timestamp: str
    load: int


class RouteLoadTrend(BaseModel):
    route_id: str
    route_name: str
    current_load: int = Field(ge=0)
    capacity: int = Field(ge=1)
    utilization_percent: float = Field(ge=0.0, le=100.0)
    trend: str = Field(description="filling | stable | emptying")
    fill_rate_per_minute: float
    estimated_full_minutes: float | None = Field(
        None, description="Minutes until capacity reached; None if stable/emptying"
    )
    snapshots: list[LoadSnapshot] = Field(default_factory=list)
    summary: str = Field(description="Voice-ready sentence for ASR")


class ShelterStatus(BaseModel):
    shelter_id: str
    name: str
    status: str = Field(description="open | closed | at_capacity")
    current_occupancy: int = Field(ge=0)
    max_capacity: int = Field(ge=1)
    occupancy_percent: float = Field(ge=0.0, le=100.0)
    services: list[str] = Field(default_factory=list)
    associated_route_ids: list[str] = Field(default_factory=list)
    summary: str = Field(description="Voice-ready sentence for ASR")


class RouteWeather(BaseModel):
    route_id: str
    route_name: str
    condition: str = Field(description="clear | rain | wind | smoke | fog")
    temperature_c: float
    wind_speed_kmh: float
    wind_direction: str
    visibility_km: float
    air_quality_index: int = Field(ge=0)
    advisory: str | None = None
    summary: str = Field(description="Voice-ready sentence for ASR")


class MetricsDashboard(BaseModel):
    threats: list[ThreatProximity]
    route_trends: list[RouteLoadTrend]
    shelters: list[ShelterStatus]
    weather: list[RouteWeather]
    overall_summary: str = Field(description="One-paragraph voice briefing")
    generated_at: str
