"""Agent endpoints — 4-agent pipeline: Assess → Risk → Route → Orchestrate."""

from fastapi import APIRouter

from app.schemas.agent_models import (
    AssessRequest,
    DisasterAssessmentOutput,
    EvaluateRiskRequest,
    OrchestrateRequest,
    OrchestratorOutput,
    PersonRiskProfile,
    RoutingOutput,
)
from app.services.agents.assess_agent import run_assessment
from app.services.agents.orchestrate_agent import orchestrate
from app.services.agents.risk_agent import evaluate_risk
from app.services.agents.route_agent import compute_routes_with_coords

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/assess", response_model=DisasterAssessmentOutput)
async def assess(request: AssessRequest) -> DisasterAssessmentOutput:
    """Agent 1: Build a disaster assessment from weather + city-state step data."""
    return await run_assessment(request)


@router.post("/evaluate-risk", response_model=PersonRiskProfile)
async def evaluate_risk_endpoint(request: EvaluateRiskRequest) -> PersonRiskProfile:
    """Agent 2: Evaluate personal risk against a disaster assessment."""
    return await evaluate_risk(request)


@router.post("/route", response_model=RoutingOutput)
async def route(request: OrchestrateRequest) -> RoutingOutput:
    """Agent 3: Compute ranked routes for a person given their risk profile.

    This is a convenience endpoint that runs Assess → Risk → Route internally.
    For the full pipeline output, use /agents/orchestrate.
    """
    result = await orchestrate(request)
    return result.routing_output


@router.post("/orchestrate", response_model=OrchestratorOutput)
async def orchestrate_endpoint(request: OrchestrateRequest) -> OrchestratorOutput:
    """Agent 4: Full pipeline — Assess → Risk → Route in one call."""
    return await orchestrate(request)
