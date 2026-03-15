from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.schemas.weather_step_models import WeatherStepMeta

CityCardSeverity = Literal["low", "medium", "high", "extreme"]
AlertUrgency = Literal[
    "notification",
    "caution",
    "warning",
    "urgent warning",
    "alert",
    "urgent alert",
    "extreme urgency alert",
]


class CityStateStepCard(BaseModel):
    id: str
    headline: str
    details: str
    severity: CityCardSeverity
    updatedAt: str
    rawData: dict[str, Any]


class CityStateAlert(BaseModel):
    id: str
    title: str
    details: str
    urgency: AlertUrgency
    category: str
    occurredAt: str
    updatedAt: str
    area: str
    source: str
    status: str = "Active"
    lat: Optional[float] = None
    lon: Optional[float] = None
    rawData: dict[str, Any]


class CityStateDatasetMetadata(BaseModel):
    dataset_name: str
    version: str
    generated_at: str
    scenario_note: str
    location: dict[str, Any]
    schema_alignment: dict[str, Any]


class CityStateStepResponse(BaseModel):
    metadata: CityStateDatasetMetadata
    step: WeatherStepMeta
    beautified: list[CityStateStepCard]
    alerts: list[CityStateAlert]
    raw: dict[str, Any]
