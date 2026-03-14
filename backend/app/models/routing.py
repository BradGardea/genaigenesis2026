from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class HazardReport(BaseModel):
    id: str = Field(default_factory=lambda: f"haz-{uuid.uuid4().hex[:8]}")
    hazard_type: str = Field(description="wildfire | flood | roadblock | chemical | other")
    location: Coordinate
    radius_meters: float = Field(ge=10, le=50000, default=500)
    description: str = ""
    reported_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    active: bool = True


class HazardZone(BaseModel):
    hazard_id: str
    polygon: dict = Field(description="GeoJSON Polygon geometry")
    hazard_type: str
    severity: str = "high"
    radius_meters: float = 500


class RouteRequest(BaseModel):
    origin: Coordinate
    destination: Coordinate
    profile: EvacuationProfileInput | None = None


class EvacuationProfileInput(BaseModel):
    family_size: int = Field(ge=1, default=1)
    vehicles: int = Field(ge=0, default=1)
    has_children: bool = False
    has_elderly: bool = False
    has_mobility_needs: bool = False


class RouteResponse(BaseModel):
    route_id: str
    geometry: dict = Field(description="GeoJSON LineString geometry")
    distance_meters: float
    duration_seconds: float
    waypoints: list[Coordinate] = Field(default_factory=list)
    hazards_avoided: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    backup_route: dict | None = Field(
        default=None, description="GeoJSON LineString of backup route"
    )


class SSEEvent(BaseModel):
    event_type: str = Field(description="reroute | hazard_added | hazard_removed | heartbeat")
    data: dict


# Allow forward reference resolution
RouteRequest.model_rebuild()
