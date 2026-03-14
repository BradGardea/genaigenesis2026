"""Pydantic models for hazard prediction endpoint responses.

Predictions are heuristic estimates combining live signals and forecast
drivers. They are NOT certified scientific outputs.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class HazardPrediction(BaseModel):
    """A single heuristic hazard risk prediction for a point location."""

    hazard_type: str = Field(description="Type of hazard (wildfire-spread, flood-risk, severe-weather-risk)")
    latitude: float
    longitude: float
    valid_from: str = Field(description="ISO 8601 prediction window start (current time)")
    valid_to: str = Field(description="ISO 8601 prediction window end")
    risk_level: str = Field(description="Overall risk level: low | medium | high")
    confidence: str = Field(description="Confidence in the assessment: low | medium | high")
    score: int = Field(description="Raw heuristic score 0-100", ge=0, le=100)
    drivers: List[str] = Field(description="Factors that contributed to the risk score")
    based_on: List[str] = Field(description="Data source IDs used in this prediction")
    summary: str = Field(description="Plain-language explanation of the risk assessment")


class PredictionSummary(BaseModel):
    """Combined hazard risk summary for a single location."""

    latitude: float
    longitude: float
    generated_at: str
    wildfire_spread: Optional[HazardPrediction] = None
    flood_risk: Optional[HazardPrediction] = None
    severe_weather_risk: Optional[HazardPrediction] = None
    note: str = (
        "Predictions are heuristic-based estimates and should not replace "
        "official government warnings or certified forecasts."
    )
