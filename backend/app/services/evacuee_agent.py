"""EvacueeAgent — state machine for a single simulated evacuee."""

from __future__ import annotations

import logging
import random
import uuid
from typing import Any

from shapely.geometry import LineString, Point

from app.models.routing import Coordinate, EvacuationProfileInput
from app.schemas.simulation_models import (
    AgentDecision,
    AgentSituation,
    AgentSnapshot,
    AgentState,
)
from app.providers.watsonx_client import generate_decision

logger = logging.getLogger(__name__)


class EvacueeAgent:
    """A single simulated evacuee with LLM-driven decision making."""

    def __init__(
        self,
        agent_id: str,
        lat: float,
        lng: float,
        dest_lat: float,
        dest_lng: float,
        profile: EvacuationProfileInput | None = None,
        watsonx_model_id: str = "ibm/granite-3.1-8b-instruct",
    ) -> None:
        self.agent_id = agent_id
        self.lat = lat
        self.lng = lng
        self.dest_lat = dest_lat
        self.dest_lng = dest_lng
        self.profile = profile or EvacuationProfileInput()
        self.watsonx_model_id = watsonx_model_id

        self.state = AgentState.idle
        self.route_id: str | None = None
        self.route_geometry: LineString | None = None
        self.route_distance_m: float = 0.0
        self.route_duration_s: float = 0.0
        self.progress: float = 0.0  # 0.0 to 1.0
        self.last_decision: AgentDecision | None = None
        self.congestion: float = 0.0
        self.rerouted_this_tick: bool = False
        self._situation_hash: str = ""

    @property
    def origin(self) -> Coordinate:
        return Coordinate(lng=self.lng, lat=self.lat)

    @property
    def destination(self) -> Coordinate:
        return Coordinate(lng=self.dest_lng, lat=self.dest_lat)

    def snapshot(self) -> AgentSnapshot:
        return AgentSnapshot(
            agent_id=self.agent_id,
            state=self.state,
            lat=self.lat,
            lng=self.lng,
            family_size=self.profile.family_size,
            vehicles=self.profile.vehicles,
            route_id=self.route_id,
            route_geometry=[[c[0], c[1]] for c in self.route_geometry.coords] if self.route_geometry else None,
            last_decision=self.last_decision,
            progress=round(self.progress, 3),
        )

    def build_situation(
        self,
        tick: int,
        nearby_hazards: list[dict],
        weather_summary: str,
    ) -> AgentSituation:
        remaining_dist = self.route_distance_m * (1.0 - self.progress) if self.route_geometry else None
        remaining_dur = self.route_duration_s * (1.0 - self.progress) if self.route_geometry else None

        return AgentSituation(
            agent_id=self.agent_id,
            state=self.state,
            lat=self.lat,
            lng=self.lng,
            family_size=self.profile.family_size,
            has_children=self.profile.has_children,
            has_elderly=self.profile.has_elderly,
            has_mobility_needs=self.profile.has_mobility_needs,
            vehicles=self.profile.vehicles,
            nearby_hazards=nearby_hazards,
            weather_summary=weather_summary,
            route_distance_remaining_m=remaining_dist,
            route_duration_remaining_s=remaining_dur,
            congestion_level=self.congestion,
            tick=tick,
        )

    def _situation_changed(self, situation: AgentSituation) -> bool:
        """Check if the situation materially changed since last decision.

        Only re-triggers on meaningful changes: state transition, hazard count
        change, or congestion crossing a 0.25-wide threshold band.
        """
        congestion_band = int(situation.congestion_level / 0.25)
        h = f"{situation.state}:{len(situation.nearby_hazards)}:{congestion_band}"
        if h != self._situation_hash:
            self._situation_hash = h
            return True
        return False

    async def decide(
        self,
        tick: int,
        nearby_hazards: list[dict],
        weather_summary: str,
    ) -> AgentDecision | None:
        """Get a decision from watsonx/rules if the situation changed."""
        if self.state in (AgentState.arrived, AgentState.sheltering):
            return None

        situation = self.build_situation(tick, nearby_hazards, weather_summary)
        if not self._situation_changed(situation):
            return None

        decision = await generate_decision(situation, self.watsonx_model_id)
        self.last_decision = decision
        return decision

    async def apply_decision(
        self,
        decision: AgentDecision,
        compute_route_fn,
        hazard_polygons: list[dict],
        crisis_traffic_factor: float = 1.5,
    ) -> None:
        """Execute the agent's decision."""
        self.rerouted_this_tick = False

        if decision.action == "depart" and self.state == AgentState.idle:
            self.state = AgentState.planning
            await self._plan_route(compute_route_fn, hazard_polygons, crisis_traffic_factor)

        elif decision.action == "reroute" and self.state == AgentState.evacuating:
            self.rerouted_this_tick = True
            self.state = AgentState.planning
            await self._plan_route(compute_route_fn, hazard_polygons, crisis_traffic_factor)

        elif decision.action == "shelter_in_place":
            self.state = AgentState.sheltering

        # "wait" → no state change

    async def _plan_route(
        self,
        compute_route_fn,
        hazard_polygons: list[dict],
        crisis_traffic_factor: float,
    ) -> None:
        """Compute a route and transition to evacuating."""
        try:
            route = await compute_route_fn(
                self.origin, self.destination, hazard_polygons, crisis_traffic_factor
            )
            self.route_id = f"sim-route-{uuid.uuid4().hex[:8]}"
            self.route_geometry = LineString(route["geometry"]["coordinates"])
            self.route_distance_m = route.get("distance", 0)
            self.route_duration_s = route.get("duration", 0)
            self.progress = 0.0
            self.state = AgentState.evacuating
            logger.info(
                "Agent %s route planned: %d coords, %.0fm",
                self.agent_id,
                len(route["geometry"]["coordinates"]),
                self.route_distance_m,
            )
        except Exception:
            logger.exception("Route planning failed for agent %s", self.agent_id)
            # Stay idle on failure so we can retry next tick
            self.state = AgentState.idle

    def advance_position(self, tick_interval_seconds: float) -> None:
        """Move agent along route geometry based on elapsed time."""
        if self.state != AgentState.evacuating or self.route_geometry is None:
            return

        if self.route_duration_s <= 0:
            self.progress = 1.0
        else:
            self.progress += tick_interval_seconds / self.route_duration_s

        if self.progress >= 1.0:
            self.progress = 1.0
            self.state = AgentState.arrived
            # Snap to destination
            self.lat = self.dest_lat
            self.lng = self.dest_lng
            return

        # Interpolate position along route geometry
        pt = self.route_geometry.interpolate(self.progress, normalized=True)
        self.lng = pt.x
        self.lat = pt.y
