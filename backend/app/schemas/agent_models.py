"""Pydantic models for the 4-agent pipeline: Assess → Risk → Route → Orchestrate."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Shared geometry types ─────────────────────────────────────────────


class LatLon(BaseModel):
    lat: float
    lon: float


class LatLng(BaseModel):
    lat: float
    lng: float


# ── Agent 1: Disaster Assessment ──────────────────────────────────────


class AssessRequest(BaseModel):
    """Input for the disaster assessment agent."""

    weather_step_index: int = Field(ge=0)
    city_state_step_index: int = Field(ge=0)


class ScenarioSnapshot(BaseModel):
    step_index: int
    step_time: str
    overall_severity: int = 0
    operational_status: str = "unknown"
    dominant_impacts: list[str] = Field(default_factory=list)


class UnsafeZone(BaseModel):
    zone_id: str
    source: Literal["city_state", "storm_focus", "storm_forecast"]
    impact_type: str
    danger_to_remain: str = "unknown"
    severity: int = 0
    valid_from: str = ""
    valid_until: str = ""
    center: LatLon
    radius_m: int = 0
    polygon: dict[str, Any] = Field(default_factory=dict)


class StormMovement(BaseModel):
    direction_deg: Optional[int] = None
    speed_kmh: Optional[float] = None
    current_center: Optional[LatLon] = None
    forecast_30min: Optional[LatLon] = None
    forecast_60min: Optional[LatLon] = None
    wind_speed_kmh: Optional[float] = None
    rainfall_mm_10min: Optional[float] = None


class ActiveAlert(BaseModel):
    id: str
    title: str
    urgency: str = "warning"
    category: str = ""
    area: str = ""
    source: str = ""


class DisasterAssessmentOutput(BaseModel):
    assessment_id: str
    generated_at: str
    scenario: ScenarioSnapshot
    unsafe_zones: list[UnsafeZone] = Field(default_factory=list)
    storm_movement: Optional[StormMovement] = None
    active_alerts: list[ActiveAlert] = Field(default_factory=list)
    total_unsafe_zones: int = 0
    summary: str = ""


# ── Agent 2: Person Risk Evaluation ──────────────────────────────────


class PersonContext(BaseModel):
    user_id: str = "anonymous"
    origin: LatLng
    destination: Optional[LatLng] = None
    vehicle: Literal["car", "motorcycle", "foot", "truck"] = "car"
    has_mobility_needs: bool = False
    has_medical_equipment: bool = False
    party_size: int = Field(default=1, ge=1)
    risk_tolerance: Literal["low", "medium", "high"] = "low"


class EvaluateRiskRequest(BaseModel):
    assessment: DisasterAssessmentOutput
    person: PersonContext


class RelevantZone(BaseModel):
    zone_id: str
    impact_type: str
    danger_to_remain: str = "unknown"
    severity: int = 0
    distance_from_origin_km: float = 0.0
    on_direct_path: bool = False
    polygon: dict[str, Any] = Field(default_factory=dict)


class SuggestedDestination(BaseModel):
    name: str
    lat: float
    lng: float
    type: str = "evacuation_center"
    distance_from_origin_km: float = 0.0
    clears_all_avoid_polygons: bool = False


class PersonRiskProfile(BaseModel):
    profile_id: str
    generated_at: str
    user_id: str
    personal_risk_level: Literal["low", "medium", "high", "critical"] = "low"
    confidence: Literal["low", "medium", "high"] = "medium"
    should_evacuate_now: bool = False
    relevant_zones: list[RelevantZone] = Field(default_factory=list)
    avoid_polygons: list[dict[str, Any]] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    routing_urgency: Literal["low", "medium", "high"] = "low"
    suggested_destinations: list[SuggestedDestination] = Field(default_factory=list)


# ── Agent 3: Routing ──────────────────────────────────────────────────


class RouteRequest(BaseModel):
    risk_profile: PersonRiskProfile
    check_isochrone: bool = False


class RankedRoute(BaseModel):
    rank: int
    route_id: str
    label: str
    geometry: dict[str, Any] = Field(default_factory=dict)
    distance_meters: float = 0.0
    duration_seconds: float = 0.0
    eta_minutes: float = 0.0
    risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    zones_crossed: list[str] = Field(default_factory=list)
    zones_avoided: list[str] = Field(default_factory=list)
    avoidance_waypoints_used: list[LatLng] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    note: str = ""


class MatrixScore(BaseModel):
    destination_index: int
    duration_seconds: float
    destination: LatLng


class RoutingOutput(BaseModel):
    routing_id: str
    generated_at: str
    user_id: str
    origin: LatLng
    destination_used: LatLng
    ranked_routes: list[RankedRoute] = Field(default_factory=list)
    matrix_scores: list[MatrixScore] = Field(default_factory=list)
    isochrone_30min: Optional[dict[str, Any]] = None
    recommendation: str = ""
    zones_on_best_route: int = 0
    total_zones_in_area: int = 0


# ── Agent 4: Orchestrator ─────────────────────────────────────────────


class OrchestrateRequest(BaseModel):
    weather_step_index: int = Field(ge=0)
    city_state_step_index: int = Field(ge=0)
    person: PersonContext
    check_isochrone: bool = False


class OrchestratorOutput(BaseModel):
    run_id: str
    generated_at: str
    total_duration_ms: float = 0.0
    disaster_assessment: DisasterAssessmentOutput
    person_risk_profile: PersonRiskProfile
    routing_output: RoutingOutput
