"""SimulationOrchestrator — drives multi-agent evacuation simulations."""

from __future__ import annotations

import asyncio
import logging
import math
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shapely.geometry import Point, Polygon

from app.models.routing import Coordinate, EvacuationProfileInput, HazardReport
from app.simulation.models import (
    AgentSnapshot,
    AgentState,
    ClusterSummary,
    SimulationConfig,
    SimulationState,
    SimulationStatus,
    SimulationSummary,
    TickMetrics,
)
from app.simulation.evacuee import EvacueeAgent
from app.simulation.evacuation_points import nearest_evacuation_point
from app.services.hazard_store import hazard_store
from app.services.mapbox_routing import compute_route, CRISIS_TRAFFIC_FACTOR
from app.simulation.metrics import MetricsCollector
from app.simulation.clock import SimulationClock
from app.services.city_state_augmentor import augment_city_state_step, maybe_inject_route_hazard
from app.services.timestep_dataset import TimestepDataset

logger = logging.getLogger(__name__)

# Agent processing concurrency limit
_AGENT_SEMAPHORE = asyncio.Semaphore(50)

CITY_STATE_TIMELINE_FILENAME = "goma_severe_storm_12h_72_timesteps.json"

# Vilankulo, Mozambique habitable land polygon.
# The town sits on the Indian Ocean coast; ocean is to the east / southeast.
# This polygon traces the land area west of the coastline where agents may spawn.
# Coordinates are (lng, lat) to match Shapely's x/y convention.
_VILANKULO_LAND_POLYGON = Polygon([
    (35.270, -21.960),   # NW corner — inland
    (35.325, -21.960),   # NE — coast north of town
    (35.330, -21.975),   # coast curving south
    (35.328, -21.990),   # coast at town center
    (35.322, -22.005),   # coast curving SW
    (35.315, -22.020),   # coast south of center
    (35.305, -22.035),   # coast continues SW
    (35.290, -22.050),   # SE corner — coast
    (35.270, -22.050),   # SW corner — inland
    (35.270, -21.960),   # close polygon
])

_MAX_SPAWN_RETRIES = 50


def _is_valid_spawn(lat: float, lng: float) -> bool:
    """Return True if the coordinate falls on land (inside the habitable polygon)."""
    pt = Point(lng, lat)
    return _VILANKULO_LAND_POLYGON.contains(pt)


def _load_timeline_total_steps() -> int:
    """Return the number of timesteps in the city state timeline dataset."""
    try:
        root = Path(__file__).resolve().parents[3]
        ds = TimestepDataset(root / "data" / CITY_STATE_TIMELINE_FILENAME)
        return ds.total_steps
    except Exception:
        logger.debug("City state timeline dataset not available")
        return 0

# In-memory registry of active simulations
simulations: dict[str, SimulationOrchestrator] = {}


class SimulationOrchestrator:
    """Manages a single simulation run: agents, clock, hazards, metrics."""

    def __init__(self, sim_id: str, config: SimulationConfig) -> None:
        self.sim_id = sim_id
        self.config = config
        self.state = SimulationState.created
        self.clock = SimulationClock(
            max_ticks=config.max_ticks,
            tick_interval_seconds=config.tick_interval_seconds,
        )
        self.metrics = MetricsCollector()
        self.agents: list[EvacueeAgent] = []
        self.event_log: list[dict] = []
        self._task: asyncio.Task | None = None
        self._sse_queues: list[asyncio.Queue] = []
        self._weather_cache: dict[tuple[float, float, int], str] = {}
        self._city_state_total_steps: int = _load_timeline_total_steps()
        self._city_state_cache: dict[int, dict] = {}
        self._forced_reroute_injected: bool = False

        self._init_agents()

    def _init_agents(self) -> None:
        """Generate randomized evacuee agents within the bounding box.

        Each agent is routed to the nearest evacuation point based on
        their spawn location.
        """
        cfg = self.config
        for i in range(cfg.num_evacuees):
            lat = random.uniform(cfg.bbox_min_lat, cfg.bbox_max_lat)
            lng = random.uniform(cfg.bbox_min_lng, cfg.bbox_max_lng)
            for _ in range(_MAX_SPAWN_RETRIES):
                if _is_valid_spawn(lat, lng):
                    break
                lat = random.uniform(cfg.bbox_min_lat, cfg.bbox_max_lat)
                lng = random.uniform(cfg.bbox_min_lng, cfg.bbox_max_lng)
            else:
                logger.warning(
                    "Agent %d: could not find valid spawn after %d retries, using last attempt",
                    i, _MAX_SPAWN_RETRIES,
                )

            evac_point = nearest_evacuation_point(lat, lng)

            profile = EvacuationProfileInput(
                family_size=random.randint(1, 5),
                vehicles=random.randint(1, 2),
                has_children=random.random() < 0.3,
                has_elderly=random.random() < 0.2,
                has_mobility_needs=random.random() < 0.1,
            )
            agent = EvacueeAgent(
                agent_id=f"agent-{i:03d}",
                lat=lat,
                lng=lng,
                dest_lat=evac_point.lat,
                dest_lng=evac_point.lng,
                dest_name=evac_point.name,
                profile=profile,
                watsonx_model_id=cfg.watsonx_model_id,
            )
            self.agents.append(agent)
        self._form_clusters()

    def _form_clusters(self) -> None:
        """Greedy one-pass proximity clustering at spawn time."""
        radius = self.config.cluster_radius_m / 111_320  # metres → degrees
        unassigned = list(self.agents)
        idx = 0
        while unassigned:
            leader = unassigned[0]
            leader.is_leader = True
            cid = f"cluster-{idx:03d}"
            leader.cluster_id = cid
            remaining = []
            for agent in unassigned[1:]:
                dlat = agent.lat - leader.lat
                dlng = (agent.lng - leader.lng) * math.cos(math.radians(leader.lat))
                if math.hypot(dlat, dlng) <= radius:
                    agent.cluster_id = cid
                    # Small offset so followers don't stack exactly on the leader's route
                    agent._leader_offset = (dlat * 0.1, dlng * 0.1)
                else:
                    remaining.append(agent)
            unassigned = remaining
            idx += 1
        logger.info(
            "Simulation %s: %d agents → %d clusters (radius=%.0fm)",
            self.sim_id, len(self.agents), idx, self.config.cluster_radius_m,
        )

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self) -> None:
        """Launch the background tick loop."""
        if self.state != SimulationState.created:
            raise RuntimeError(f"Cannot start simulation in state {self.state}")
        self.state = SimulationState.running
        self._task = asyncio.create_task(self._run_loop())

    def stop(self) -> None:
        """Cancel the simulation."""
        self.state = SimulationState.stopped
        if self._task and not self._task.done():
            self._task.cancel()

    def subscribe_sse(self) -> asyncio.Queue:
        """Create and return a new SSE queue for streaming tick events."""
        q: asyncio.Queue = asyncio.Queue()
        self._sse_queues.append(q)
        return q

    def unsubscribe_sse(self, q: asyncio.Queue) -> None:
        self._sse_queues = [x for x in self._sse_queues if x is not q]

    # ── Tick loop ──────────────────────────────────────────────

    async def _run_loop(self) -> None:
        try:
            while not self.clock.is_expired and self.state == SimulationState.running:
                tick_start = asyncio.get_event_loop().time()
                tick = self.clock.advance()
                await self._process_tick(tick)

                # Check if all agents are in terminal states
                if all(
                    a.state in (AgentState.arrived, AgentState.sheltering)
                    for a in self.agents
                ):
                    logger.info("All agents reached terminal state at tick %d", tick)
                    break

                # Subtract processing time so ticks stay on schedule
                elapsed = asyncio.get_event_loop().time() - tick_start
                remaining = max(0, self.config.tick_interval_seconds - elapsed)
                if remaining > 0:
                    await asyncio.sleep(remaining)

        except asyncio.CancelledError:
            logger.info("Simulation %s cancelled", self.sim_id)
        except Exception:
            logger.exception("Simulation %s failed", self.sim_id)
        finally:
            if self.state == SimulationState.running:
                self.state = SimulationState.completed
            # Signal SSE clients that simulation ended
            for q in self._sse_queues:
                await q.put({"event": "simulation_end", "data": {"sim_id": self.sim_id}})

    async def _process_tick(self, tick: int) -> None:
        """Execute one simulation tick."""
        # 1. Inject scheduled hazards
        await self._inject_scheduled_hazards(tick)

        # 1b. Advance city state timeline — generate urban impacts and inject route hazards
        city_state_step = await self._advance_city_state(tick)

        # 1c. Inject city_state hazards directly into hazard_store
        if city_state_step:
            self._inject_city_state_hazards(city_state_step, tick)

        # 1d. For small sims, inject a hazard on an agent's route to force a reroute
        if (
            not self._forced_reroute_injected
            and len(self.agents) < 10
            and tick >= 4
        ):
            for a in self.agents:
                if (
                    a.state == AgentState.evacuating
                    and a.route_geometry
                    and 0.2 <= a.progress <= 0.6
                ):
                    pt = a.route_geometry.interpolate(0.7, normalized=True)
                    report = HazardReport(
                        hazard_type="roadblock",
                        location=Coordinate(lng=pt.x, lat=pt.y),
                        radius_meters=300,
                        description=f"Road closure ahead of {a.agent_id}",
                    )
                    hazard_store.add_hazard(report)
                    self._forced_reroute_injected = True
                    a._situation_hash = ""
                    logger.info(
                        "Forced reroute hazard injected on %s route at tick %d (%.4f, %.4f)",
                        a.agent_id, tick, pt.y, pt.x,
                    )
                    event = {
                        "event": "hazard_injected",
                        "data": {"hazard_id": report.id, "tick": tick, "type": "roadblock"},
                    }
                    self.event_log.append(event)
                    for q in self._sse_queues:
                        await q.put(event)
                    break

        # 1e. Clear per-tick flags and event buffers on all agents
        for a in self.agents:
            a.events_this_tick = []


        # 2. Fetch weather (cached per tick + rounded coords)
        weather_summary = await self._get_weather_for_tick(tick)

        # 3. Get active hazard state (includes any hazards injected by city state)
        active_zones = hazard_store.get_active_hazards()
        hazard_polygons = [z.polygon for z in active_zones]
        nearby_hazards = [
            {"id": z.hazard_id, "type": z.hazard_type} for z in active_zones
        ]

        # Merge city state flood/closure impacts as additional nearby hazard context
        if city_state_step:
            city_hazards = self._extract_city_state_hazards(city_state_step)
            nearby_hazards.extend(city_hazards)

        # 4. Compute congestion from co-located agents
        self._compute_congestion()

        # 5. Process agents concurrently — leaders get LLM decisions, followers mirror
        reroutes = 0
        traffic_factor = self._weather_traffic_factor(weather_summary)

        leaders = [a for a in self.agents if a.is_leader or a.cluster_id is None]
        followers = [a for a in self.agents if not a.is_leader and a.cluster_id is not None]

        async def process_agent(agent: EvacueeAgent) -> int:
            async with _AGENT_SEMAPHORE:
                decision = await agent.decide(tick, nearby_hazards, weather_summary, active_zones)
                if decision:
                    await agent.apply_decision(
                        decision, compute_route, hazard_polygons, traffic_factor
                    )

                agent.advance_position(self.config.virtual_seconds_per_tick)
                return 1 if agent.rerouted_this_tick else 0

        results = await asyncio.gather(
            *(process_agent(a) for a in leaders), return_exceptions=True
        )
        for r in results:
            if isinstance(r, int):
                reroutes += r

        # Process followers synchronously — only mirror fresh leader decisions
        leader_by_cluster = {a.cluster_id: a for a in leaders if a.cluster_id}
        leader_decided_this_tick = {
            a.cluster_id for a in leaders
            if a.cluster_id and (a.rerouted_this_tick or a._last_decision_tick == tick)
        }
        for follower in followers:
            leader = leader_by_cluster.get(follower.cluster_id)
            # Only apply leader decision on the tick the leader actually made one
            if leader and leader.last_decision and follower.cluster_id in leader_decided_this_tick:
                await follower.apply_leader_decision(
                    leader.last_decision,
                    compute_route,
                    hazard_polygons,
                    traffic_factor,
                    follower._leader_offset,
                )
                if follower.rerouted_this_tick:
                    reroutes += 1
            follower.advance_position(self.config.virtual_seconds_per_tick)

        # 6. Compute cluster summaries
        cluster_map: dict[str, list] = {}
        for a in self.agents:
            key = a.cluster_id if a.cluster_id else a.agent_id
            cluster_map.setdefault(key, []).append(a)

        summaries: list[ClusterSummary] = []
        for cid, members in cluster_map.items():
            leader_agents = [a for a in members if a.is_leader]
            if not leader_agents:
                continue
            summaries.append(ClusterSummary(
                cluster_id=cid,
                leader_id=leader_agents[0].agent_id,
                member_count=len(members),
                centroid_lat=sum(a.lat for a in members) / len(members),
                centroid_lng=sum(a.lng for a in members) / len(members),
            ))

        # 6b. Collect and broadcast agent activity events (capped at 50)
        agent_events: list[dict] = []
        for a in self.agents:
            agent_events.extend(a.events_this_tick)
        if agent_events:
            if len(agent_events) > 50:
                agent_events = agent_events[:50]
            ae_event = {
                "event": "agent_events",
                "data": {"tick": tick, "events": agent_events},
            }
            for q in self._sse_queues:
                await q.put(ae_event)

        # 7. Collect metrics
        tick_metrics = self.metrics.collect(
            tick=tick,
            agents=self.agents,
            active_hazard_count=len(active_zones),
            reroutes_this_tick=reroutes,
            clusters=summaries,
        )

        # 7. Log and broadcast
        event = {
            "event": "tick",
            "data": tick_metrics.model_dump(),
        }
        self.event_log.append(event)
        for q in self._sse_queues:
            await q.put(event)

        # 7b. Broadcast city state update if available
        if city_state_step:
            cs = city_state_step.get("city_state", {})
            city_event = {
                "event": "city_state",
                "data": {
                    "tick": tick,
                    "step_index": self._tick_to_city_step(tick),
                    "overall_severity": cs.get("overall_severity", 0),
                    "operational_status": cs.get("operational_status", "unknown"),
                    "danger_to_remain": cs.get("danger_to_remain", "unknown"),
                    "dominant_impacts": cs.get("dominant_impacts", []),
                    "recommended_action": cs.get("recommended_action", ""),
                    "city_services": cs.get("city_services", {}),
                },
            }
            self.event_log.append(city_event)
            for q in self._sse_queues:
                await q.put(city_event)

    def _tick_to_city_step(self, tick: int) -> int:
        """Map a simulation tick to a city state step index.

        Scales linearly so tick 1 → step 0, tick max_ticks → last step.
        """
        if self._city_state_total_steps <= 0:
            return 0
        max_ticks = max(self.config.max_ticks, 1)
        return min(
            int((tick - 1) / max_ticks * self._city_state_total_steps),
            self._city_state_total_steps - 1,
        )

    async def _advance_city_state(self, tick: int) -> dict | None:
        """Generate city state impacts for this tick's mapped step."""
        if self._city_state_total_steps <= 0:
            return None

        step_index = self._tick_to_city_step(tick)

        # Avoid re-processing the same step
        if step_index in self._city_state_cache:
            return self._city_state_cache[step_index]

        try:
            raw_step = {"time": "", "city_state": {}}
            augmented = augment_city_state_step(
                raw_step,
                step_index=step_index,
                total_steps=self._city_state_total_steps,
            )
            await maybe_inject_route_hazard(
                augmented,
                step_index=step_index,
                total_steps=self._city_state_total_steps,
            )
            self._city_state_cache[step_index] = augmented
            logger.info(
                "City state step %d generated for tick %d: severity=%s",
                step_index,
                tick,
                augmented.get("city_state", {}).get("overall_severity", "?"),
            )
            return augmented
        except Exception:
            logger.debug("City state augmentation failed for tick %d", tick)
            return None

    @staticmethod
    def _extract_city_state_hazards(city_state_step: dict) -> list[dict]:
        """Extract flood and road closure events from city state as nearby hazard dicts."""
        cs = city_state_step.get("city_state", {})
        areas = cs.get("affected_areas", [])
        hazards: list[dict] = []
        for area in areas:
            impact_type = area.get("impact_type", "")
            if impact_type in ("road_closure", "flooding", "debris", "structure_damage") and int(area.get("severity", 0)) >= 25:
                hazards.append({
                    "id": area.get("node_id", "unknown"),
                    "type": impact_type,
                    "severity": area.get("severity", 0),
                    "source": "city_state",
                })
        return hazards

    def _inject_city_state_hazards(self, city_state_step: dict, tick: int) -> int:
        """Inject hazards from city_state affected areas directly into hazard_store.

        Returns the number of new hazards injected.
        """
        cs = city_state_step.get("city_state", {})
        areas = cs.get("affected_areas", [])
        injected = 0
        for area in areas:
            impact_type = area.get("impact_type", "")
            severity = int(area.get("severity", 0))
            if impact_type not in ("road_closure", "flooding", "debris", "structure_damage") or severity < 25:
                continue
            lat = area.get("lat")
            lon = area.get("lon")
            if lat is None or lon is None:
                continue
            node_id = str(area.get("node_id", f"cs-{tick}-{injected}"))
            # Skip if already injected (keyed by node_id)
            cache_key = f"cs-hazard-{node_id}"
            if cache_key in self._city_state_cache:
                continue
            self._city_state_cache[cache_key] = True
            type_map = {"road_closure": "roadblock", "flooding": "flood", "debris": "debris", "structure_damage": "collapse"}
            radius = float(area.get("radius_m", 200))
            report = HazardReport(
                hazard_type=type_map.get(impact_type, "hazard"),
                location=Coordinate(lng=float(lon), lat=float(lat)),
                radius_meters=radius,
                description=f"City state {impact_type} (severity {severity}) at tick {tick}",
            )
            hazard_store.add_hazard(report)
            injected += 1
            logger.info(
                "Injected city_state hazard %s at tick %d: %s severity=%d",
                node_id, tick, impact_type, severity,
            )
        return injected

    async def _inject_scheduled_hazards(self, tick: int) -> None:
        """Add hazards scheduled for this tick."""
        for h in self.config.hazard_schedule:
            if h.tick == tick:
                report = HazardReport(
                    hazard_type=h.hazard_type,
                    location=Coordinate(lng=h.lng, lat=h.lat),
                    radius_meters=h.radius_meters,
                    description=h.description or f"Scheduled hazard at tick {tick}",
                )
                zone = hazard_store.add_hazard(report)
                await hazard_store.notify_affected_routes(zone)
                logger.info(
                    "Injected hazard %s at tick %d: %s",
                    report.id, tick, h.hazard_type,
                )
                event = {
                    "event": "hazard_injected",
                    "data": {"hazard_id": report.id, "tick": tick, "type": h.hazard_type},
                }
                self.event_log.append(event)
                for q in self._sse_queues:
                    await q.put(event)

    def inject_hazard(self, hazard_type: str, lat: float, lng: float, radius_meters: float) -> str:
        """Manually inject a hazard mid-simulation. Returns hazard ID."""
        report = HazardReport(
            hazard_type=hazard_type,
            location=Coordinate(lng=lng, lat=lat),
            radius_meters=radius_meters,
            description="Manual mid-simulation hazard",
        )
        zone = hazard_store.add_hazard(report)
        # Force all evacuating agents to reconsider next tick
        for agent in self.agents:
            if agent.state == AgentState.evacuating:
                agent._situation_hash = ""  # Reset so decision is triggered
        return report.id

    async def _get_weather_for_tick(self, tick: int) -> str:
        """Get a weather summary, cached per tick and region center."""
        center_lat = round((self.config.bbox_min_lat + self.config.bbox_max_lat) / 2, 2)
        center_lng = round((self.config.bbox_min_lng + self.config.bbox_max_lng) / 2, 2)
        cache_key = (center_lat, center_lng, tick)

        if cache_key in self._weather_cache:
            return self._weather_cache[cache_key]

        try:
            from app.services.forecasts_service import get_hourly_forecast

            forecast = await get_hourly_forecast(center_lat, center_lng)
            if forecast.hourly:
                h = forecast.hourly[0]
                summary = (
                    f"Temp {h.temperature_c}°C, "
                    f"Wind {h.wind_speed_kmh} km/h, "
                    f"Precip {h.precipitation_probability}%, "
                    f"Humidity {h.relative_humidity}%"
                )
            else:
                summary = "Weather data unavailable"
        except Exception:
            logger.debug("Weather fetch failed for tick %d", tick)
            summary = "Weather data unavailable"

        self._weather_cache[cache_key] = summary
        return summary

    def _compute_congestion(self) -> None:
        """Simple congestion: more co-located evacuating agents = higher congestion."""
        evacuating = [a for a in self.agents if a.state == AgentState.evacuating]
        if not evacuating:
            return

        for agent in self.agents:
            if agent.state != AgentState.evacuating:
                agent.congestion = 0.0
                continue
            nearby = sum(
                1
                for other in evacuating
                if other.agent_id != agent.agent_id
                and abs(other.lat - agent.lat) < 0.005
                and abs(other.lng - agent.lng) < 0.005
            )
            agent.congestion = min(1.0, nearby / max(len(evacuating), 1))

    @staticmethod
    def _weather_traffic_factor(weather_summary: str) -> float:
        """Increase crisis traffic factor based on severe weather."""
        factor = CRISIS_TRAFFIC_FACTOR
        lower = weather_summary.lower()
        # High precipitation probability
        try:
            if "precip" in lower:
                # Extract percentage
                for part in lower.split(","):
                    if "precip" in part:
                        pct = int("".join(c for c in part if c.isdigit()))
                        if pct > 70:
                            factor += 0.3
                        break
        except (ValueError, IndexError):
            pass
        # High wind
        try:
            if "wind" in lower:
                for part in lower.split(","):
                    if "wind" in part:
                        speed = float("".join(c for c in part if c.isdigit() or c == "."))
                        if speed > 60:
                            factor += 0.2
                        break
        except (ValueError, IndexError):
            pass
        return factor

    # ── Status / Summary ──────────────────────────────────────

    def status(self) -> SimulationStatus:
        return SimulationStatus(
            sim_id=self.sim_id,
            state=self.state,
            current_tick=self.clock.current_tick,
            max_ticks=self.config.max_ticks,
            agents=[a.snapshot() for a in self.agents],
            latest_metrics=self.metrics.latest,
        )

    def summary(self) -> SimulationSummary:
        return SimulationSummary(
            sim_id=self.sim_id,
            state=self.state,
            total_ticks=self.clock.current_tick,
            total_agents=len(self.agents),
            agents_arrived=sum(1 for a in self.agents if a.state == AgentState.arrived),
            agents_sheltering=sum(1 for a in self.agents if a.state == AgentState.sheltering),
            total_reroutes=self.metrics.total_reroutes,
            metrics_history=self.metrics.history,
        )
