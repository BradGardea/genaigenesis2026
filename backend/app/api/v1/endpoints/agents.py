"""Agent endpoints — placeholder skeleton for AI-assisted briefings.

Agent reasoning is NOT yet implemented. These endpoints return stub responses
and are scaffolded for future integration with an LLM agent pipeline.
"""

from fastapi import APIRouter

from app.schemas.agent_models import AgentBriefingRequest, AgentBriefingResponse
from app.services import meteorologist_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/meteorologist/briefing", response_model=AgentBriefingResponse)
async def meteorologist_briefing(
    request: AgentBriefingRequest,
) -> AgentBriefingResponse:
    """Request a meteorological situational briefing (agent placeholder).

    Currently returns a stub response. This endpoint will be connected to
    an LLM agent pipeline with live signal and forecast tool-use in a
    future release.
    """
    return await meteorologist_service.generate_briefing(request)
