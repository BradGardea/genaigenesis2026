"""Per-tick metrics aggregation for evacuation simulations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.simulation.models import AgentState, ClusterSummary, TickMetrics

if TYPE_CHECKING:
    from app.simulation.evacuee import EvacueeAgent


class MetricsCollector:
    """Collects and stores per-tick simulation metrics."""

    def __init__(self) -> None:
        self.history: list[TickMetrics] = []
        self.total_reroutes: int = 0

    def collect(
        self,
        tick: int,
        agents: list[EvacueeAgent],
        active_hazard_count: int,
        reroutes_this_tick: int,
        clusters: list[ClusterSummary] | None = None,
    ) -> TickMetrics:
        self.total_reroutes += reroutes_this_tick

        state_counts = {s: 0 for s in AgentState}
        congestion_values: list[float] = []
        for agent in agents:
            state_counts[agent.state] += 1
            congestion_values.append(agent.congestion)

        avg_congestion = (
            sum(congestion_values) / len(congestion_values)
            if congestion_values
            else 0.0
        )

        metrics = TickMetrics(
            tick=tick,
            agents_idle=state_counts[AgentState.idle],
            agents_planning=state_counts[AgentState.planning],
            agents_evacuating=state_counts[AgentState.evacuating],
            agents_arrived=state_counts[AgentState.arrived],
            agents_sheltering=state_counts[AgentState.sheltering],
            reroutes_this_tick=reroutes_this_tick,
            active_hazards=active_hazard_count,
            avg_congestion=round(avg_congestion, 3),
            clusters=clusters or [],
        )
        self.history.append(metrics)
        return metrics

    @property
    def latest(self) -> TickMetrics | None:
        return self.history[-1] if self.history else None
