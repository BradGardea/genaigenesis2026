from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertSignal(BaseModel):
    id: str
    signal_type: str = Field(
        description="Risk signal type (seismic, drought, wildfire, tornado, etc.)"
    )
    value: str
    severity: str
    source: str


@router.get("/signals", response_model=list[AlertSignal])
def list_signals() -> list[AlertSignal]:
    return [
        AlertSignal(
            id="sig-1",
            signal_type="drought",
            value="critical dry conditions",
            severity="high",
            source="weather-pipeline",
        ),
        AlertSignal(
            id="sig-2",
            signal_type="seismic",
            value="elevated micro-tremors",
            severity="medium",
            source="geologic-feed",
        ),
    ]

