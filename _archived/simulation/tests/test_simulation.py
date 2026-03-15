"""Unit + integration tests for the evacuation simulation system."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.models.routing import Coordinate, EvacuationProfileInput
from app.schemas.simulation_models import (
    AgentDecision,
    AgentSituation,
    AgentState,
    ScheduledHazard,
    SimulationConfig,
    SimulationState,
    TickMetrics,
)
from app.services.evacuee_agent import EvacueeAgent
from app.services.metrics_collector import MetricsCollector
from app.services.simulation_clock import SimulationClock


# ── SimulationClock tests ──────────────────────────────────


class TestSimulationClock:
    def test_initial_state(self):
        clock = SimulationClock(max_ticks=10, tick_interval_seconds=1.0)
        assert clock.current_tick == 0
        assert not clock.is_expired
        assert clock.elapsed_virtual_seconds == 0.0

    def test_advance(self):
        clock = SimulationClock(max_ticks=3)
        assert clock.advance() == 1
        assert clock.advance() == 2
        assert clock.advance() == 3
        assert clock.is_expired

    def test_elapsed_virtual_seconds(self):
        clock = SimulationClock(max_ticks=10, tick_interval_seconds=5.0)
        clock.advance()
        clock.advance()
        assert clock.elapsed_virtual_seconds == 10.0


# ── EvacueeAgent tests ────────────────────────────────────


class TestEvacueeAgent:
    def _make_agent(self, **kwargs) -> EvacueeAgent:
        defaults = dict(
            agent_id="agent-001",
            lat=34.05,
            lng=-118.25,
            dest_lat=34.10,
            dest_lng=-118.10,
        )
        defaults.update(kwargs)
        return EvacueeAgent(**defaults)

    def test_initial_state(self):
        agent = self._make_agent()
        assert agent.state == AgentState.idle
        assert agent.progress == 0.0
        assert agent.route_id is None

    def test_snapshot(self):
        agent = self._make_agent()
        snap = agent.snapshot()
        assert snap.agent_id == "agent-001"
        assert snap.state == AgentState.idle
        assert snap.progress == 0.0

    def test_build_situation(self):
        agent = self._make_agent()
        situation = agent.build_situation(
            tick=5,
            nearby_hazards=[{"id": "haz-1", "type": "wildfire"}],
            weather_summary="Temp 30°C, Wind 20 km/h",
        )
        assert situation.tick == 5
        assert situation.state == AgentState.idle
        assert len(situation.nearby_hazards) == 1
        assert "30°C" in situation.weather_summary

    @pytest.mark.asyncio
    async def test_decide_idle_no_hazards(self):
        """Idle agent with no hazards should decide to depart (rule-based)."""
        agent = self._make_agent()
        with patch("app.providers.watsonx_client.settings") as mock_settings:
            mock_settings.watsonx_api_key = ""  # Force rule-based
            decision = await agent.decide(tick=1, nearby_hazards=[], weather_summary="")
        assert decision is not None
        assert decision.action == "depart"

    @pytest.mark.asyncio
    async def test_decide_idle_with_hazard(self):
        """Idle agent near hazard should depart urgently."""
        agent = self._make_agent()
        with patch("app.providers.watsonx_client.settings") as mock_settings:
            mock_settings.watsonx_api_key = ""
            decision = await agent.decide(
                tick=1,
                nearby_hazards=[{"id": "haz-1", "type": "wildfire"}],
                weather_summary="",
            )
        assert decision is not None
        assert decision.action == "depart"
        assert decision.urgency >= 8

    @pytest.mark.asyncio
    async def test_apply_decision_shelter(self):
        """Shelter decision should change state."""
        agent = self._make_agent()
        decision = AgentDecision(action="shelter_in_place", reasoning="test", urgency=7)
        await agent.apply_decision(decision, AsyncMock(), [])
        assert agent.state == AgentState.sheltering

    @pytest.mark.asyncio
    async def test_apply_decision_depart(self):
        """Depart decision should plan route and start evacuating."""
        agent = self._make_agent()
        mock_route = {
            "geometry": {
                "type": "LineString",
                "coordinates": [[-118.25, 34.05], [-118.20, 34.07], [-118.10, 34.10]],
            },
            "distance": 5000,
            "duration": 600,
        }
        mock_compute = AsyncMock(return_value=mock_route)
        decision = AgentDecision(action="depart", reasoning="go", urgency=5)
        await agent.apply_decision(decision, mock_compute, [])
        assert agent.state == AgentState.evacuating
        assert agent.route_id is not None
        assert agent.route_distance_m == 5000

    def test_advance_position(self):
        """Agent should move along route geometry."""
        agent = self._make_agent()
        agent.state = AgentState.evacuating
        from shapely.geometry import LineString

        agent.route_geometry = LineString([(-118.25, 34.05), (-118.10, 34.10)])
        agent.route_duration_s = 100
        agent.route_distance_m = 5000

        agent.advance_position(tick_interval_seconds=50)
        assert agent.progress == pytest.approx(0.5, abs=0.01)
        assert agent.state == AgentState.evacuating

    def test_advance_to_arrival(self):
        """Agent at end of route should arrive."""
        agent = self._make_agent()
        agent.state = AgentState.evacuating
        from shapely.geometry import LineString

        agent.route_geometry = LineString([(-118.25, 34.05), (-118.10, 34.10)])
        agent.route_duration_s = 100
        agent.progress = 0.95

        agent.advance_position(tick_interval_seconds=10)
        assert agent.state == AgentState.arrived
        assert agent.progress == 1.0

    def test_no_advance_when_idle(self):
        """Idle agents should not move."""
        agent = self._make_agent()
        agent.advance_position(tick_interval_seconds=10)
        assert agent.lat == 34.05
        assert agent.lng == -118.25


# ── MetricsCollector tests ─────────────────────────────────


class TestMetricsCollector:
    def test_collect(self):
        collector = MetricsCollector()
        agents = [
            self._mock_agent(AgentState.idle),
            self._mock_agent(AgentState.evacuating, congestion=0.5),
            self._mock_agent(AgentState.arrived),
        ]
        metrics = collector.collect(tick=1, agents=agents, active_hazard_count=2, reroutes_this_tick=1)
        assert metrics.tick == 1
        assert metrics.agents_idle == 1
        assert metrics.agents_evacuating == 1
        assert metrics.agents_arrived == 1
        assert metrics.active_hazards == 2
        assert metrics.reroutes_this_tick == 1
        assert collector.total_reroutes == 1

    def test_history(self):
        collector = MetricsCollector()
        agents = [self._mock_agent(AgentState.idle)]
        collector.collect(tick=0, agents=agents, active_hazard_count=0, reroutes_this_tick=0)
        collector.collect(tick=1, agents=agents, active_hazard_count=1, reroutes_this_tick=0)
        assert len(collector.history) == 2
        assert collector.latest.tick == 1

    def _mock_agent(self, state: AgentState, congestion: float = 0.0):
        agent = EvacueeAgent(
            agent_id="test",
            lat=0, lng=0,
            dest_lat=1, dest_lng=1,
        )
        agent.state = state
        agent.congestion = congestion
        return agent


# ── watsonx client tests ──────────────────────────────────


class TestWatsonxClient:
    def test_parse_decision_valid(self):
        from app.providers.watsonx_client import _parse_decision

        text = '{"action": "depart", "reasoning": "hazard nearby", "urgency": 8}'
        decision = _parse_decision(text)
        assert decision is not None
        assert decision.action == "depart"
        assert decision.urgency == 8

    def test_parse_decision_with_markdown(self):
        from app.providers.watsonx_client import _parse_decision

        text = '```json\n{"action": "reroute", "reasoning": "blocked", "urgency": 7}\n```'
        decision = _parse_decision(text)
        assert decision is not None
        assert decision.action == "reroute"

    def test_parse_decision_invalid(self):
        from app.providers.watsonx_client import _parse_decision

        assert _parse_decision("not json at all") is None
        assert _parse_decision('{"wrong_key": "value"}') is None

    def test_rule_based_idle_no_hazards(self):
        from app.providers.watsonx_client import _rule_based_decision

        situation = AgentSituation(
            agent_id="a", state=AgentState.idle, lat=0, lng=0
        )
        decision = _rule_based_decision(situation)
        assert decision.action == "depart"

    def test_rule_based_evacuating_with_hazard(self):
        from app.providers.watsonx_client import _rule_based_decision

        situation = AgentSituation(
            agent_id="a",
            state=AgentState.evacuating,
            lat=0, lng=0,
            nearby_hazards=[{"id": "h1", "type": "wildfire"}],
        )
        decision = _rule_based_decision(situation)
        assert decision.action == "reroute"

    def test_rule_based_severe_weather(self):
        from app.providers.watsonx_client import _rule_based_decision

        situation = AgentSituation(
            agent_id="a",
            state=AgentState.idle,
            lat=0, lng=0,
            weather_summary="Extreme tornado warning",
        )
        decision = _rule_based_decision(situation)
        assert decision.action == "shelter_in_place"

    def test_prompt_construction(self):
        from app.providers.watsonx_client import _build_user_prompt

        situation = AgentSituation(
            agent_id="a",
            state=AgentState.evacuating,
            lat=34.05, lng=-118.25,
            family_size=3,
            has_children=True,
            weather_summary="Clear skies",
            tick=5,
        )
        prompt = _build_user_prompt(situation)
        assert "34.0500" in prompt
        assert "children" in prompt
        assert "Clear skies" in prompt


# ── Integration test ──────────────────────────────────────


class TestSimulationIntegration:
    @pytest.mark.asyncio
    async def test_mini_simulation(self):
        """3-tick, 2-agent simulation with mocked Mapbox + watsonx."""
        mock_route = {
            "geometry": {
                "type": "LineString",
                "coordinates": [[-118.25, 34.05], [-118.20, 34.07], [-118.10, 34.10]],
            },
            "distance": 5000,
            "duration": 4,  # Very short so agents arrive quickly
        }

        config = SimulationConfig(
            num_evacuees=2,
            max_ticks=3,
            tick_interval_seconds=0.1,
            bbox_min_lat=34.0,
            bbox_max_lat=34.1,
            bbox_min_lng=-118.3,
            bbox_max_lng=-118.2,
            destination_lat=34.10,
            destination_lng=-118.10,
            hazard_schedule=[
                ScheduledHazard(tick=2, hazard_type="wildfire", lat=34.05, lng=-118.25, radius_meters=500)
            ],
        )

        with patch("app.services.simulation_orchestrator.compute_route", new_callable=AsyncMock) as mock_compute, \
             patch("app.services.simulation_orchestrator.SimulationOrchestrator._get_weather_for_tick", new_callable=AsyncMock) as mock_weather, \
             patch("app.providers.watsonx_client.settings") as mock_settings:

            mock_compute.return_value = mock_route
            mock_weather.return_value = "Clear skies"
            mock_settings.watsonx_api_key = ""

            from app.services.simulation_orchestrator import SimulationOrchestrator

            orch = SimulationOrchestrator("test-sim", config)
            assert len(orch.agents) == 2
            assert orch.state == SimulationState.created

            # Run the simulation
            orch.start()
            # Wait for it to complete (short ticks)
            for _ in range(50):
                await asyncio.sleep(0.1)
                if orch.state in (SimulationState.completed, SimulationState.stopped):
                    break

            assert orch.state == SimulationState.completed
            assert orch.clock.current_tick >= 1

            summary = orch.summary()
            assert summary.total_agents == 2
            assert len(orch.metrics.history) > 0
