"""Placeholder Pydantic models for agent-based endpoints.

These models define the interface for future AI-assisted briefing agents.
No agent reasoning is implemented yet.
"""

from typing import Optional
from pydantic import BaseModel


class AgentBriefingRequest(BaseModel):
    """Input parameters for a meteorological agent briefing request."""

    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    focus: Optional[str] = None  # e.g. "wildfire", "flood", "all"


class AgentBriefingResponse(BaseModel):
    """Stub response from the meteorological briefing agent."""

    status: str
    message: str
    inputs_received: dict
    note: str = (
        "Agent reasoning is not yet implemented. "
        "This is a placeholder response for API scaffolding."
    )
