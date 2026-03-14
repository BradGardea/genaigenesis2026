"""Meteorologist agent service — delegates to the agent implementation."""

from app.schemas.agent_models import AgentBriefingRequest, AgentBriefingResponse
from app.services.agents.meteorologist_agent import generate_meteorologist_briefing


async def generate_briefing(request: AgentBriefingRequest) -> AgentBriefingResponse:
    """Generate a meteorological briefing via agent reasoning."""
    return await generate_meteorologist_briefing(request)
