"""Agent endpoints for AI-assisted briefings."""

from fastapi import APIRouter

from app.schemas.agent_models import (
    AgentBriefingRequest,
    AgentBriefingResponse,
    DecisionRequest,
    RouteMatrixRequest,
)
from app.services import meteorologist_service
from app.services.agents.decision_agent import generate_decision
from app.services.agents.hazard_analyst_agent import generate_hazard_briefing
from app.services.agents.routing_agent import generate_route_matrix

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/meteorologist/briefing", response_model=AgentBriefingResponse)
async def meteorologist_briefing(
    request: AgentBriefingRequest,
) -> AgentBriefingResponse:
    """Request a meteorological situational briefing."""
    return await meteorologist_service.generate_briefing(request)


@router.post("/hazard-analyst/briefing", response_model=AgentBriefingResponse)
async def hazard_analyst_briefing(
    request: AgentBriefingRequest,
) -> AgentBriefingResponse:
    """Request a multi-hazard risk assessment briefing."""
    return await generate_hazard_briefing(request)


@router.post("/routing-analyst/matrix", response_model=AgentBriefingResponse)
async def routing_analyst_matrix(
    request: RouteMatrixRequest,
) -> AgentBriefingResponse:
    """Compute a matrix of feasible routes scored against hazards and weather."""
    return await generate_route_matrix(request)


@router.post("/decision/choose-route", response_model=AgentBriefingResponse)
async def decision_choose_route(
    request: DecisionRequest,
) -> AgentBriefingResponse:
    """Choose the best evacuation route based on personal circumstances.

    Orchestrates the routing analyst, hazard analyst, and meteorologist
    agents in parallel, then synthesizes a personalized decision that
    accounts for family composition, mobility needs, supplies, and
    current conditions.
    """
    return await generate_decision(request)
