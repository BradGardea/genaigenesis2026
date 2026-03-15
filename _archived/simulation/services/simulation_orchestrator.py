"""SimulationOrchestrator — drives multi-agent evacuation simulations."""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.routing import Coordinate, EvacuationProfileInput, HazardReport
from app.schemas.simulation_models import (
    AgentSnapshot,
    AgentState,
    SimulationConfig,
    SimulationState,
    SimulationStatus,
    SimulationSummary,
    TickMetrics,
)
from app.services.evacuee_agent import EvacueeAgent
from app.services.hazard_store import hazard_store
from app.services.mapbox_routing import compute_route, CRISIS_TRAFFIC_FACTOR
from app.services.metrics_collector import MetricsCollector
from app.services.simulation_clock import SimulationClock

logger = logging.getLogger(__name__)

# Agent processing concurrency limit
_AGENT_SEMAPHORE = asyncio.Semaphore(10)

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

        self._init_agents()

    def _init_agents(self) -> None:
        """Generate randomized evacuee agents within the bounding box."""
        cfg = self.config
        for i in range(cfg.num_evacuees):
            lat = random.uniform(cfg.bbox_min_lat, cfg.bbox_max_lat)
            lng = random.uniform(cfg.bbox_min_lng, cfg.bbox_max_lng)
            profile = EvacuationProfileInput(
                family_size=random.randint(1, 5),
                vehicles=random.randint(0, 2),
                has_children=random.random() < 0.3,
                has_elderly=random.random() < 0.2,
                has_mobility_needs=random.random() < 0.1,
            )
            agent = EvacueeAgent(
                agent_id=f"agent-{i:03d}",
                lat=lat,
                lng=lng,
                dest_lat=cfg.destination_lat,
                dest_lng=cfg.destination_lng,
                profile=profile,
                watsonx_model_id=cfg.watsonx_model_id,
            )
            self.agents.append(agent)

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
                tick = self.clock.advance()
                await self._process_tick(tick)

                # Check if all agents are in terminal states
                if all(
                    a.state in (AgentState.arrived, AgentState.sheltering)
                    for a in self.agents
                ):
                    logger.info("All agents reached terminal state at tick %d", tick)
                    break

                await asyncio.sleep(self.config.tick_interval_seconds)

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

        # 2. Fetch weather (cached per tick + rounded coords)
        weather_summary = await self._get_weather_for_tick(tick)

        # 3. Get active hazard state
        active_zones = hazard_store.get_active_hazards()
        hazard_polygons = [z.polygon for z in active_zones]
        nearby_hazards = [
            {"id": z.hazard_id, "type": z.hazard_type} for z in active_zones
        ]

        # 4. Compute congestion from co-located agents
        self._compute_congestion()

        # 5. Process agents concurrently
        reroutes = 0

        async def process_agent(agent: EvacueeAgent) -> int:
            async with _AGENT_SEMAPHORE:
                # Stagger Mapbox calls to avoid rate-limit bursts
                await asyncio.sleep(random.uniform(0, 0.5))

                traffic_factor = self._weather_traffic_factor(weather_summary)

                decision = await agent.decide(tick, nearby_hazards, weather_summary)
                if decision:
                    await agent.apply_decision(
                        decision, compute_route, hazard_polygons, traffic_factor
                    )

                agent.advance_position(self.config.virtual_seconds_per_tick)
                return 1 if agent.rerouted_this_tick else 0

        results = await asyncio.gather(
            *(process_agent(a) for a in self.agents), return_exceptions=True
        )
        for r in results:
            if isinstance(r, int):
                reroutes += r

        # 6. Collect metrics
        tick_metrics = self.metrics.collect(
            tick=tick,
            agents=self.agents,
            active_hazard_count=len(active_zones),
            reroutes_this_tick=reroutes,
        )

        # 7. Log and broadcast
        event = {
            "event": "tick",
            "data": tick_metrics.model_dump(),
        }
        self.event_log.append(event)
        for q in self._sse_queues:
            await q.put(event)

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
