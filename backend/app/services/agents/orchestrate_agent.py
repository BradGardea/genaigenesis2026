"""Agent 4 — Orchestrator.

Chains Agent 1 (Assess) → Agent 2 (Risk) → Agent 3 (Route) and
returns the combined output with timing.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from app.schemas.agent_models import (
    AssessRequest,
    EvaluateRiskRequest,
    LatLng,
    OrchestrateRequest,
    OrchestratorOutput,
)
from app.services.agents.assess_agent import run_assessment
from app.services.agents.risk_agent import evaluate_risk
from app.services.agents.route_agent import compute_routes_with_coords


async def orchestrate(request: OrchestrateRequest) -> OrchestratorOutput:
    """Execute the full Assess → Risk → Route pipeline."""
    run_id = f"orch-{uuid.uuid4().hex[:8]}"
    start = time.monotonic()

    # ── Agent 1: Disaster Assessment ──────────────────────────
    assess_req = AssessRequest(
        weather_step_index=request.weather_step_index,
        city_state_step_index=request.city_state_step_index,
    )
    assessment = await run_assessment(assess_req)

    # ── Agent 2: Person Risk Evaluation ───────────────────────
    risk_req = EvaluateRiskRequest(
        assessment=assessment,
        person=request.person,
    )
    risk_profile = await evaluate_risk(risk_req)

    # ── Agent 3: Routing ──────────────────────────────────────
    origin = LatLng(lat=request.person.origin.lat, lng=request.person.origin.lng)
    destination = origin  # default to origin if no destination
    if request.person.destination:
        destination = LatLng(
            lat=request.person.destination.lat,
            lng=request.person.destination.lng,
        )
    elif risk_profile.suggested_destinations:
        sd = risk_profile.suggested_destinations[0]
        destination = LatLng(lat=sd.lat, lng=sd.lng)

    routing_output = await compute_routes_with_coords(
        risk_profile=risk_profile,
        origin=origin,
        destination=destination,
        check_isochrone=request.check_isochrone,
    )

    elapsed_ms = round((time.monotonic() - start) * 1000, 1)
    now = datetime.now(timezone.utc).isoformat()

    return OrchestratorOutput(
        run_id=run_id,
        generated_at=now,
        total_duration_ms=elapsed_ms,
        disaster_assessment=assessment,
        person_risk_profile=risk_profile,
        routing_output=routing_output,
    )
