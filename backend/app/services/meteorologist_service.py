"""Meteorologist agent service — placeholder skeleton.

This module will house agent orchestration logic for AI-assisted
meteorological briefings. Currently returns a stub response.

TODO: Connect to an LLM agent workflow with tool-use, live signal
      retrieval, and forecast data when the agent layer is built out.
"""

from app.schemas.agent_models import AgentBriefingRequest, AgentBriefingResponse


async def generate_briefing(request: AgentBriefingRequest) -> AgentBriefingResponse:
    """Generate a meteorological briefing via agent reasoning.

    Currently a placeholder — returns a stub response with the inputs echoed.
    """
    return AgentBriefingResponse(
        status="not_implemented",
        message=(
            "Agent reasoning pipeline is not yet implemented. "
            "This endpoint is scaffolded for future AI-assisted briefings."
        ),
        inputs_received={
            "location": request.location,
            "latitude": request.latitude,
            "longitude": request.longitude,
            "focus": request.focus,
        },
    )
