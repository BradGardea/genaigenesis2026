from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

WeatherSeverity = Literal["low", "medium", "high", "extreme"]
WeatherConditionType = Literal[
    "cyclone",
    "thunderstorm",
    "heavy_rain",
    "high_wind",
    "flooding",
    "storm_surge",
    "low_visibility",
    "pressure",
    "tornado",
    "general",
]


class WeatherStepCard(BaseModel):
    id: str
    headline: str
    details: str
    severity: WeatherSeverity
    conditionType: WeatherConditionType
    updatedAt: str
    rawData: dict[str, Any]


class WeatherDatasetMetadata(BaseModel):
    dataset_name: str
    version: str
    generated_at: str
    scenario_note: str
    location: dict[str, Any]
    schema_alignment: dict[str, Any]


class WeatherStepMeta(BaseModel):
    step_index: int
    step_time: str
    total_steps: int
    has_next: bool
    next_step_index: int | None


class WeatherStepResponse(BaseModel):
    metadata: WeatherDatasetMetadata
    step: WeatherStepMeta
    beautified: list[WeatherStepCard]
    raw: dict[str, Any]
