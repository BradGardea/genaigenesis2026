"""Pydantic models for the agent briefing system."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────────────

class AgentBriefingRequest(BaseModel):
    """Input parameters for an agent briefing request."""

    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    focus: Optional[str] = None  # e.g. "wildfire", "flood", "all"


# ── Domain outputs (typed per-agent) ────────────────────────────────

class MeteorologistOutput(BaseModel):
    summary: str
    risk_level: str = Field(description="low / medium / high / extreme")
    active_alerts_count: int = 0
    key_threats: list[str] = []
    forecast_outlook: str = ""
    recommended_actions: list[str] = []


class HazardAnalystOutput(BaseModel):
    summary: str
    wildfire_risk: str = "low"
    flood_risk: str = "low"
    severe_weather_risk: str = "low"
    active_hazard_zones: int = 0
    evacuation_recommended: bool = False
    reasoning: str = ""


# ── Routing agent ────────────────────────────────────────────────────

class RouteMatrixRequest(BaseModel):
    """Input for the routing analyst agent."""

    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    max_alternatives: int = Field(default=3, ge=1, le=5)


class RouteCandidateOutput(BaseModel):
    """A single scored route candidate."""

    label: str = Field(description="e.g. 'Direct', 'Northern bypass'")
    geometry: dict = Field(description="GeoJSON LineString")
    distance_meters: float = 0
    duration_seconds: float = 0
    feasibility_score: float = Field(default=50, description="0-100, higher is better")
    hazard_exposure: str = Field(default="unknown", description="none / low / medium / high")
    weather_impact: str = Field(default="unknown", description="none / low / medium / high")
    hazards_crossed: list[str] = []
    weather_risks: list[str] = []
    reasoning: str = ""


class RoutingAnalystOutput(BaseModel):
    """Full output from the routing analyst agent."""

    summary: str
    recommended_route: str = Field(description="Label of the best candidate")
    candidates: list[RouteCandidateOutput] = []
    overall_assessment: str = ""
    evacuation_urgency: str = Field(default="low", description="low / medium / high / critical")


# ── Decision agent ───────────────────────────────────────────────────

class DecisionRequest(BaseModel):
    """User circumstances + origin/destination for the decision agent."""

    # Location
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    # Personal circumstances
    family_size: int = Field(default=1, ge=1)
    vehicles: int = Field(default=1, ge=0)
    has_children: bool = False
    has_elderly: bool = False
    has_mobility_needs: bool = False
    supplies_hours: float = Field(default=24.0, ge=0, description="Hours of supplies on hand")
    medical_needs: bool = False
    pets: bool = False
    # Optional: max alternatives to evaluate
    max_alternatives: int = Field(default=3, ge=1, le=5)


class DecisionOutput(BaseModel):
    """Final actionable decision tailored to the user's circumstances."""

    action: str = Field(description="evacuate_now / evacuate_soon / shelter_in_place / monitor")
    chosen_route: str = Field(default="", description="Label of the selected route")
    chosen_route_geometry: dict = Field(default_factory=dict, description="GeoJSON LineString")
    chosen_route_distance_meters: float = 0
    chosen_route_duration_seconds: float = 0
    departure_window: str = Field(default="not yet", description="immediately / within_1h / within_4h / not_yet")
    urgency: int = Field(default=5, ge=1, le=10)
    reasoning: str = ""
    preparation_steps: list[str] = []
    warnings: list[str] = []
    confidence: str = Field(default="medium", description="high / medium / low")
    hazard_summary: str = ""
    weather_summary: str = ""


# ── Unified envelope response ───────────────────────────────────────

class AgentBriefingResponse(BaseModel):
    """Envelope returned by every agent endpoint."""

    agent_type: str
    status: str = Field(description="ok / fallback / error")
    briefing: str = ""
    structured_data: dict[str, Any] = {}
    data_sources: list[str] = []
    generated_at: datetime = Field(default_factory=datetime.utcnow)
