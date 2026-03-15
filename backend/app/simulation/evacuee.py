"""EvacueeAgent — state machine for a single simulated evacuee."""

from __future__ import annotations

import logging
import random
import uuid
from typing import Any

from shapely.geometry import LineString, Point

from app.models.routing import Coordinate, EvacuationProfileInput
from app.simulation.models import (
    AgentDecision,
    AgentSituation,
    AgentSnapshot,
    AgentState,
)
from app.simulation.decision import generate_decision
from app.simulation.evacuation_points import sorted_evacuation_points

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
        dest_name: str = "",
        profile: EvacuationProfileInput | None = None,
        watsonx_model_id: str = "meta-llama/llama-3-3-70b-instruct",
    ) -> None:
        self.agent_id = agent_id
        self.lat = lat
        self.lng = lng
        self.dest_lat = dest_lat
        self.dest_lng = dest_lng
        self.dest_name = dest_name
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
        self._last_decision_tick: int = -999

        # Per-tick event feed
        self.events_this_tick: list[dict] = []

        # Cluster fields
        self.cluster_id: str | None = None
        self.is_leader: bool = False
        self._leader_offset: tuple[float, float] = (0.0, 0.0)

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
            cluster_id=self.cluster_id,
            is_leader=self.is_leader,
            dest_name=self.dest_name,
            dest_lat=self.dest_lat,
            dest_lng=self.dest_lng,
        )

    def _filter_relevant_hazards(
        self,
        nearby_hazards: list[dict],
        hazard_zones: list,
    ) -> list[dict]:
        """Keep only hazards whose polygon intersects the agent's remaining route or is near the agent."""
        from shapely.geometry import shape as shp

        if not self.route_geometry or self.state != AgentState.evacuating:
            # Not on a route — proximity check to agent position
            agent_pt = Point(self.lng, self.lat)
            relevant = []
            for zone in hazard_zones:
                try:
                    geom = shp(zone.polygon) if hasattr(zone, "polygon") else zone
                    if agent_pt.distance(geom) < 0.01:  # ~1km
                        relevant.append({"id": zone.hazard_id, "type": zone.hazard_type})
                except Exception:
                    pass
            return relevant

        # Extract the actual remaining portion of the route geometry
        try:
            cut_point = self.route_geometry.interpolate(self.progress, normalized=True)
            # Get all coords from the route, keep only those ahead of current progress
            coords = list(self.route_geometry.coords)
            remaining_coords = [(cut_point.x, cut_point.y)]
            for coord in coords:
                pt = Point(coord)
                frac = self.route_geometry.project(pt, normalized=True)
                if frac >= self.progress:
                    remaining_coords.append(coord)
            if len(remaining_coords) < 2:
                remaining_coords = [(cut_point.x, cut_point.y), coords[-1]]
            remaining_route = LineString(remaining_coords)
        except Exception:
            remaining_route = self.route_geometry

        relevant = []
        for zone in hazard_zones:
            try:
                geom = shp(zone.polygon) if hasattr(zone, "polygon") else zone
                if remaining_route.intersects(geom):
                    relevant.append({"id": zone.hazard_id, "type": zone.hazard_type})
            except Exception:
                pass
        return relevant

    def _filter_route_hazard_polygons(self, hazard_polygons: list[dict]) -> list[dict]:
        """Return only hazard polygons that intersect the agent's remaining route."""
        if not self.route_geometry or not hazard_polygons:
            return hazard_polygons
        from shapely.geometry import shape as shp
        try:
            coords = list(self.route_geometry.coords)
            remaining_coords = []
            for coord in coords:
                pt = Point(coord)
                frac = self.route_geometry.project(pt, normalized=True)
                if frac >= self.progress - 0.05:
                    remaining_coords.append(coord)
            if len(remaining_coords) < 2:
                return hazard_polygons
            remaining = LineString(remaining_coords)
        except Exception:
            return hazard_polygons

        relevant = []
        for poly in hazard_polygons:
            try:
                geom = shp(poly) if isinstance(poly, dict) else poly
                if remaining.intersects(geom):
                    relevant.append(poly)
            except Exception:
                pass
        return relevant

    def _pick_best_evacuation_point(
        self,
        hazard_polygons: list[dict],
    ) -> bool:
        """Switch to a better evacuation point if current dest is blocked or a closer one exists.

        Returns True if the destination was changed.
        """
        from shapely.geometry import shape as shp

        candidates = sorted_evacuation_points(self.lat, self.lng)
        if not candidates:
            return False

        current_dest = (self.dest_lat, self.dest_lng)

        # Check if current destination is blocked: any hazard polygon covers it
        current_blocked = False
        dest_pt = Point(self.dest_lng, self.dest_lat)
        for poly in hazard_polygons:
            try:
                geom = shp(poly) if isinstance(poly, dict) else poly
                if geom.contains(dest_pt) or dest_pt.distance(geom) < 0.002:  # ~220m
                    current_blocked = True
                    break
            except Exception:
                pass

        if current_blocked:
            # Pick the closest evacuation point that isn't blocked
            for ep, dist_km in candidates:
                if (ep.lat, ep.lng) == current_dest:
                    continue
                ep_pt = Point(ep.lng, ep.lat)
                blocked = False
                for poly in hazard_polygons:
                    try:
                        geom = shp(poly) if isinstance(poly, dict) else poly
                        if geom.contains(ep_pt) or ep_pt.distance(geom) < 0.002:
                            blocked = True
                            break
                    except Exception:
                        pass
                if not blocked:
                    logger.info(
                        "Agent %s switching dest from %s to %s (old dest blocked)",
                        self.agent_id, self.dest_name, ep.name,
                    )
                    self.dest_lat = ep.lat
                    self.dest_lng = ep.lng
                    self.dest_name = ep.name
                    return True
            # All points blocked — keep current
            return False

        # Current dest not blocked — check if a closer unblocked point exists
        closest_ep, closest_dist = candidates[0]
        if (closest_ep.lat, closest_ep.lng) != current_dest:
            # A closer point exists — switch to it
            ep_pt = Point(closest_ep.lng, closest_ep.lat)
            ep_blocked = False
            for poly in hazard_polygons:
                try:
                    geom = shp(poly) if isinstance(poly, dict) else poly
                    if geom.contains(ep_pt) or ep_pt.distance(geom) < 0.002:
                        ep_blocked = True
                        break
                except Exception:
                    pass
            if not ep_blocked:
                logger.info(
                    "Agent %s switching dest from %s to %s (closer from current position)",
                    self.agent_id, self.dest_name, closest_ep.name,
                )
                self.dest_lat = closest_ep.lat
                self.dest_lng = closest_ep.lng
                self.dest_name = closest_ep.name
                return True

        return False

    def build_situation(
        self,
        tick: int,
        nearby_hazards: list[dict],
        weather_summary: str,
        hazard_zones: list | None = None,
    ) -> AgentSituation:
        remaining_dist = self.route_distance_m * (1.0 - self.progress) if self.route_geometry else None
        remaining_dur = self.route_duration_s * (1.0 - self.progress) if self.route_geometry else None

        # Filter to hazards actually relevant to this agent's route
        if hazard_zones:
            filtered_hazards = self._filter_relevant_hazards(nearby_hazards, hazard_zones)
        else:
            filtered_hazards = nearby_hazards

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
            nearby_hazards=filtered_hazards,
            weather_summary=weather_summary,
            route_distance_remaining_m=remaining_dist,
            route_duration_remaining_s=remaining_dur,
            congestion_level=self.congestion,
            tick=tick,
        )

    _RE_EVAL_INTERVAL = 2  # re-evaluate every N ticks if situation unchanged

    def _situation_changed(self, situation: AgentSituation) -> bool:
        """Check if the situation materially changed since last decision.

        Re-triggers on state transition, hazard count change, congestion band
        shift, or if the agent has been sitting in the same state for
        ``_RE_EVAL_INTERVAL`` ticks (prevents permanent stalls).
        """
        congestion_band = int(situation.congestion_level / 0.25)
        h = f"{situation.state}:{len(situation.nearby_hazards)}:{congestion_band}"
        if h != self._situation_hash:
            self._situation_hash = h
            self._last_decision_tick = situation.tick
            return True
        if situation.tick - self._last_decision_tick >= self._RE_EVAL_INTERVAL:
            self._last_decision_tick = situation.tick
            return True
        return False

    async def decide(
        self,
        tick: int,
        nearby_hazards: list[dict],
        weather_summary: str,
        hazard_zones: list | None = None,
    ) -> AgentDecision | None:
        """Get a decision from watsonx/rules if the situation changed."""
        if self.state in (AgentState.arrived, AgentState.sheltering):
            return None

        # Fast-path: idle agents depart immediately on tick 1 without LLM call
        if self.state == AgentState.idle and tick <= 2:
            decision = AgentDecision(
                action="depart",
                reasoning="Evacuation order — departing immediately",
                urgency=7,
            )
            self.last_decision = decision
            self._last_decision_tick = tick
            return decision

        situation = self.build_situation(tick, nearby_hazards, weather_summary, hazard_zones)
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
            self.events_this_tick.append({
                "type": "depart",
                "agent_id": self.agent_id,
                "reasoning": decision.reasoning,
                "urgency": decision.urgency,
                "dest_name": self.dest_name,
            })
            self.state = AgentState.planning
            await self._plan_route(compute_route_fn, hazard_polygons, crisis_traffic_factor)

        elif decision.action == "reroute" and self.state == AgentState.evacuating:
            # Save old route in case reroute fails
            old_route_id = self.route_id
            old_geometry = self.route_geometry
            old_distance = self.route_distance_m
            old_duration = self.route_duration_s
            old_progress = self.progress
            old_dest_lat = self.dest_lat
            old_dest_lng = self.dest_lng
            old_dest_name = self.dest_name

            # Only pass hazards near the agent's route to avoid slow Mapbox retries
            relevant_polys = self._filter_route_hazard_polygons(hazard_polygons)

            # Consider switching to a better evacuation point
            dest_changed = self._pick_best_evacuation_point(hazard_polygons)

            self.rerouted_this_tick = True
            self.state = AgentState.planning
            # Reroute from current position, not original spawn
            await self._plan_route_from(
                self.lat, self.lng, compute_route_fn, relevant_polys, crisis_traffic_factor
            )

            if self.state == AgentState.evacuating and self.route_id != old_route_id:
                # Reroute succeeded — emit event
                reasoning = decision.reasoning
                if dest_changed:
                    reasoning = f"Rerouted to {self.dest_name} — {decision.reasoning}"
                self.events_this_tick.append({
                    "type": "reroute",
                    "agent_id": self.agent_id,
                    "reasoning": reasoning,
                    "urgency": decision.urgency,
                    "dest_name": self.dest_name,
                })
            else:
                # Reroute failed — restore old route and destination
                logger.warning("Agent %s reroute failed, continuing on old route", self.agent_id)
                self.route_id = old_route_id
                self.route_geometry = old_geometry
                self.route_distance_m = old_distance
                self.route_duration_s = old_duration
                self.progress = old_progress
                self.dest_lat = old_dest_lat
                self.dest_lng = old_dest_lng
                self.dest_name = old_dest_name
                self.state = AgentState.evacuating
                self.rerouted_this_tick = False

        elif decision.action == "shelter_in_place":
            self.events_this_tick.append({
                "type": "shelter_in_place",
                "agent_id": self.agent_id,
                "reasoning": decision.reasoning,
                "urgency": decision.urgency,
            })
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
            logger.info(
                "Agent %s planning route: origin=(%.5f,%.5f) dest=(%.5f,%.5f)",
                self.agent_id, self.lat, self.lng, self.dest_lat, self.dest_lng,
            )
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
                "Agent %s route planned OK: %d coords, %.0fm, %.0fs",
                self.agent_id,
                len(route["geometry"]["coordinates"]),
                self.route_distance_m,
                self.route_duration_s,
            )
        except Exception:
            logger.exception("Route planning failed for agent %s", self.agent_id)
            self.state = AgentState.idle
            self._situation_hash = ""  # allow retry next tick

    async def _plan_route_from(
        self,
        lat: float,
        lng: float,
        compute_route_fn,
        hazard_polygons: list[dict],
        crisis_traffic_factor: float,
    ) -> None:
        """Compute a route from an explicit origin instead of self.lat/lng."""
        origin = Coordinate(lng=lng, lat=lat)
        destination = self.destination
        try:
            route = await compute_route_fn(origin, destination, hazard_polygons, crisis_traffic_factor)
            self.route_id = f"sim-route-{uuid.uuid4().hex[:8]}"
            self.route_geometry = LineString(route["geometry"]["coordinates"])
            self.route_distance_m = route.get("distance", 0)
            self.route_duration_s = route.get("duration", 0)
            self.progress = 0.0
            self.state = AgentState.evacuating

        except Exception:
            logger.exception("Route planning failed for follower agent %s", self.agent_id)
            self.state = AgentState.idle
            self._situation_hash = ""

    async def apply_leader_decision(
        self,
        decision: AgentDecision,
        compute_route_fn,
        hazard_polygons: list[dict],
        crisis_traffic_factor: float,
        origin_offset: tuple[float, float],
    ) -> None:
        """Mirror a cluster leader's decision without calling the LLM."""
        self.last_decision = decision
        self.rerouted_this_tick = False

        if decision.action == "depart" and self.state == AgentState.idle:
            self.events_this_tick.append({
                "type": "depart",
                "agent_id": self.agent_id,
                "reasoning": decision.reasoning,
                "urgency": decision.urgency,
                "dest_name": self.dest_name,
            })
            self.state = AgentState.planning
            offset_lat = self.lat + origin_offset[0]
            offset_lng = self.lng + origin_offset[1]
            await self._plan_route_from(offset_lat, offset_lng, compute_route_fn, hazard_polygons, crisis_traffic_factor)

        elif decision.action == "reroute" and self.state == AgentState.evacuating:
            old_route_id = self.route_id
            old_geometry = self.route_geometry
            old_distance = self.route_distance_m
            old_duration = self.route_duration_s
            old_progress = self.progress
            old_dest_lat = self.dest_lat
            old_dest_lng = self.dest_lng
            old_dest_name = self.dest_name

            # Consider switching to a better evacuation point
            dest_changed = self._pick_best_evacuation_point(hazard_polygons)

            self.rerouted_this_tick = True
            self.state = AgentState.planning
            await self._plan_route_from(
                self.lat + origin_offset[0],
                self.lng + origin_offset[1],
                compute_route_fn,
                hazard_polygons,
                crisis_traffic_factor,
            )

            if self.state == AgentState.evacuating and self.route_id != old_route_id:
                reasoning = decision.reasoning
                if dest_changed:
                    reasoning = f"Rerouted to {self.dest_name} — {decision.reasoning}"
                self.events_this_tick.append({
                    "type": "reroute",
                    "agent_id": self.agent_id,
                    "reasoning": reasoning,
                    "urgency": decision.urgency,
                    "dest_name": self.dest_name,
                })
            else:
                logger.warning("Follower %s reroute failed, continuing on old route", self.agent_id)
                self.route_id = old_route_id
                self.route_geometry = old_geometry
                self.route_distance_m = old_distance
                self.route_duration_s = old_duration
                self.progress = old_progress
                self.dest_lat = old_dest_lat
                self.dest_lng = old_dest_lng
                self.dest_name = old_dest_name
                self.state = AgentState.evacuating
                self.rerouted_this_tick = False

        elif decision.action == "shelter_in_place":
            self.events_this_tick.append({
                "type": "shelter_in_place",
                "agent_id": self.agent_id,
                "reasoning": decision.reasoning,
                "urgency": decision.urgency,
            })
            self.state = AgentState.sheltering

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
            self.events_this_tick.append({
                "type": "arrived",
                "agent_id": self.agent_id,
                "dest_name": self.dest_name,
            })
            # Snap to destination
            self.lat = self.dest_lat
            self.lng = self.dest_lng
            return

        # Interpolate position along route geometry
        pt = self.route_geometry.interpolate(self.progress, normalized=True)
        self.lng = pt.x
        self.lat = pt.y
