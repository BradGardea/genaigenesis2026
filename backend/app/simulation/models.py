"""Pydantic models for the multi-user evacuation simulation."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AgentState(str, Enum):
    idle = "idle"
    planning = "planning"
    evacuating = "evacuating"
    arrived = "arrived"
    sheltering = "sheltering"


class SimulationState(str, Enum):
    created = "created"
    running = "running"
    completed = "completed"
    stopped = "stopped"


class ScheduledHazard(BaseModel):
    """A hazard to inject at a specific tick."""

    tick: int = Field(ge=0)
    hazard_type: str = "wildfire"
    lat: float
    lng: float
    radius_meters: float = 1000
    description: str = ""


class SimulationConfig(BaseModel):
    """Configuration for a simulation run."""

    num_evacuees: int = Field(ge=1, le=1500, default=5)
    cluster_radius_m: float = Field(default=500.0, description="Proximity radius for cluster formation (metres)")
    # Bounding box: agents start within this region (default: Vilankulo, Mozambique)
    bbox_min_lat: float = Field(default=-22.050)
    bbox_max_lat: float = Field(default=-21.960)
    bbox_min_lng: float = Field(default=35.270)
    bbox_max_lng: float = Field(default=35.330)
    # Fallback destination if no evacuation point is found (default: inland Vilankulo)
    destination_lat: float = Field(default=-22.000)
    destination_lng: float = Field(default=35.200)
    # Tick configuration
    tick_interval_seconds: float = Field(ge=0.1, default=2.0, description="Real-world sleep between ticks (seconds)")
    virtual_seconds_per_tick: float = Field(ge=1.0, default=600.0, description="Simulated travel time per tick (seconds)")
    max_ticks: int = Field(ge=1, le=1000, default=72)
    # Scheduled hazards
    hazard_schedule: list[ScheduledHazard] = Field(default_factory=list)
    # watsonx model override
    watsonx_model_id: str = "meta-llama/llama-3-3-70b-instruct"


class AgentDecision(BaseModel):
    """Decision returned by the LLM or rule engine."""

    action: Literal["depart", "wait", "reroute", "shelter_in_place"]
    reasoning: str = ""
    urgency: int = Field(ge=1, le=10, default=5)


class AgentSituation(BaseModel):
    """Snapshot of what the agent perceives at a given tick."""

    agent_id: str
    state: AgentState
    lat: float
    lng: float
    family_size: int = 1
    has_children: bool = False
    has_elderly: bool = False
    has_mobility_needs: bool = False
    vehicles: int = 1
    nearby_hazards: list[dict] = Field(default_factory=list)
    weather_summary: str = ""
    route_distance_remaining_m: float | None = None
    route_duration_remaining_s: float | None = None
    congestion_level: float = 0.0
    tick: int = 0


class AgentSnapshot(BaseModel):
    """Public view of an agent at a point in time."""

    agent_id: str
    state: AgentState
    lat: float
    lng: float
    family_size: int = 1
    vehicles: int = 1
    route_id: str | None = None
    route_geometry: list[list[float]] | None = None
    last_decision: AgentDecision | None = None
    progress: float = Field(
        default=0.0, ge=0.0, le=1.0, description="0=start, 1=arrived"
    )
    cluster_id: str | None = None
    is_leader: bool = False
    dest_name: str = ""
    dest_lat: float | None = None
    dest_lng: float | None = None


class ClusterSummary(BaseModel):
    """Aggregated view of a proximity cluster."""

    cluster_id: str
    leader_id: str
    member_count: int
    centroid_lat: float
    centroid_lng: float


class TickMetrics(BaseModel):
    """Aggregated metrics for a single tick."""

    tick: int
    agents_idle: int = 0
    agents_planning: int = 0
    agents_evacuating: int = 0
    agents_arrived: int = 0
    agents_sheltering: int = 0
    reroutes_this_tick: int = 0
    active_hazards: int = 0
    avg_congestion: float = 0.0
    clusters: list[ClusterSummary] = []


class SimulationStatus(BaseModel):
    """Current simulation state returned by the status endpoint."""

    sim_id: str
    state: SimulationState
    current_tick: int = 0
    max_ticks: int
    agents: list[AgentSnapshot] = Field(default_factory=list)
    latest_metrics: TickMetrics | None = None


class SimulationSummary(BaseModel):
    """Final summary after simulation completes."""

    sim_id: str
    state: SimulationState
    total_ticks: int
    total_agents: int
    agents_arrived: int
    agents_sheltering: int
    total_reroutes: int
    metrics_history: list[TickMetrics] = Field(default_factory=list)
