"""REST + SSE endpoints for controlling and observing evacuation simulations."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.simulation.models import (
    SimulationConfig,
    SimulationState,
    SimulationStatus,
    SimulationSummary,
)
from app.simulation.orchestrator import SimulationOrchestrator, simulations

router = APIRouter(prefix="/simulation", tags=["simulation"])


class CreateResponse(BaseModel):
    sim_id: str
    state: str
    num_agents: int


class InjectHazardRequest(BaseModel):
    hazard_type: str = "wildfire"
    lat: float
    lng: float
    radius_meters: float = 1000


class InjectHazardResponse(BaseModel):
    hazard_id: str
    sim_id: str


class SimulationListItem(BaseModel):
    sim_id: str
    state: SimulationState
    current_tick: int
    num_agents: int


# ── Endpoints ──────────────────────────────────────────────


@router.post("/create", response_model=CreateResponse)
async def create_simulation(config: SimulationConfig) -> CreateResponse:
    """Create a new simulation from configuration."""
    sim_id = f"sim-{uuid.uuid4().hex[:8]}"
    orch = SimulationOrchestrator(sim_id, config)
    simulations[sim_id] = orch
    return CreateResponse(
        sim_id=sim_id,
        state=orch.state.value,
        num_agents=len(orch.agents),
    )


@router.post("/{sim_id}/start")
async def start_simulation(sim_id: str) -> dict:
    """Launch the background tick loop for a created simulation."""
    orch = _get_sim(sim_id)
    try:
        orch.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"sim_id": sim_id, "state": orch.state.value}


@router.get("/{sim_id}/status", response_model=SimulationStatus)
async def get_status(sim_id: str) -> SimulationStatus:
    """Get current simulation state and agent snapshots."""
    return _get_sim(sim_id).status()


@router.get("/{sim_id}/stream")
async def stream_events(sim_id: str, request: Request) -> StreamingResponse:
    """SSE stream of tick events for a running simulation."""
    orch = _get_sim(sim_id)
    queue = orch.subscribe_sse()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    event_type = event.get("event", "tick")
                    data = event.get("data", {})
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                    if event_type == "simulation_end":
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            orch.unsubscribe_sse(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{sim_id}/inject-hazard", response_model=InjectHazardResponse)
async def inject_hazard(sim_id: str, body: InjectHazardRequest) -> InjectHazardResponse:
    """Manually inject a hazard into a running simulation."""
    orch = _get_sim(sim_id)
    if orch.state != SimulationState.running:
        raise HTTPException(status_code=409, detail="Simulation is not running")
    hazard_id = orch.inject_hazard(body.hazard_type, body.lat, body.lng, body.radius_meters)
    return InjectHazardResponse(hazard_id=hazard_id, sim_id=sim_id)


@router.post("/{sim_id}/stop")
async def stop_simulation(sim_id: str) -> dict:
    """Cancel a running simulation."""
    orch = _get_sim(sim_id)
    orch.stop()
    return {"sim_id": sim_id, "state": orch.state.value}


@router.get("/{sim_id}/summary", response_model=SimulationSummary)
async def get_summary(sim_id: str) -> SimulationSummary:
    """Get final metrics summary (available after completion)."""
    orch = _get_sim(sim_id)
    if orch.state not in (SimulationState.completed, SimulationState.stopped):
        raise HTTPException(
            status_code=409,
            detail="Summary only available after simulation completes or is stopped",
        )
    return orch.summary()


@router.get("/list", response_model=list[SimulationListItem])
async def list_simulations() -> list[SimulationListItem]:
    """List all simulations."""
    return [
        SimulationListItem(
            sim_id=sid,
            state=orch.state,
            current_tick=orch.clock.current_tick,
            num_agents=len(orch.agents),
        )
        for sid, orch in simulations.items()
    ]


# ── Helpers ────────────────────────────────────────────────


def _get_sim(sim_id: str) -> SimulationOrchestrator:
    orch = simulations.get(sim_id)
    if orch is None:
        raise HTTPException(status_code=404, detail=f"Simulation {sim_id} not found")
    return orch
