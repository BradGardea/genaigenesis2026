from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/events", tags=["events"])


class DetectedEvent(BaseModel):
    id: str
    title: str
    location: str
    severity: str
    source: str
    detected_at: str


@router.get("/active", response_model=list[DetectedEvent])
def active_events() -> list[DetectedEvent]:
    return [
        DetectedEvent(
            id="evt-1",
            title="Wildfire near North Ridge",
            location="North Ridge",
            severity="high",
            source="dispatch-audio+social-correlation",
            detected_at="2026-03-09T21:40:00Z",
        )
    ]

