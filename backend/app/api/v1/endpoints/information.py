from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/information", tags=["information"])

Relationship = Literal["dependent", "guardian", "friend", "acquaintance"]

RELATIONSHIP_TRUST: dict[Relationship, int] = {
    "dependent": 3,
    "guardian": 3,
    "friend": 2,
    "acquaintance": 1,
}

RECIPROCAL_RELATIONSHIP: dict[Relationship, Relationship] = {
    "dependent": "guardian",
    "guardian": "dependent",
    "friend": "friend",
    "acquaintance": "acquaintance",
}


class InfoAlert(BaseModel):
    id: str
    title: str
    details: str
    urgency: str
    category: str
    occurredAt: str
    updatedAt: str
    area: str
    source: str


class EvacuationPlan(BaseModel):
    id: str
    title: str
    successProbability: int = Field(ge=0, le=100)
    summary: str
    steps: list[str]
    packingList: list[str]


class UserConnection(BaseModel):
    id: str
    ownerPhone: str
    contactPhone: str
    relationship: Relationship
    trustLevel: int
    updatedAt: str


class ConnectionCreateRequest(BaseModel):
    ownerPhone: str
    contactPhone: str
    relationship: Relationship


class ConnectionCreateResponse(BaseModel):
    primary: UserConnection
    reciprocal: UserConnection


class SavedInformation(BaseModel):
    id: str
    title: str
    note: str
    updatedAt: str


class WeatherUpdate(BaseModel):
    id: str
    headline: str
    details: str
    severity: str
    updatedAt: str


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _upsert_connection(
    records: list[UserConnection],
    owner_phone: str,
    contact_phone: str,
    relationship: Relationship,
) -> UserConnection:
    for index, record in enumerate(records):
        if record.ownerPhone == owner_phone and record.contactPhone == contact_phone:
            updated = UserConnection(
                id=record.id,
                ownerPhone=owner_phone,
                contactPhone=contact_phone,
                relationship=relationship,
                trustLevel=RELATIONSHIP_TRUST[relationship],
                updatedAt=_utc_now_iso(),
            )
            records[index] = updated
            return updated

    created = UserConnection(
        id=f"conn-{uuid4().hex[:8]}",
        ownerPhone=owner_phone,
        contactPhone=contact_phone,
        relationship=relationship,
        trustLevel=RELATIONSHIP_TRUST[relationship],
        updatedAt=_utc_now_iso(),
    )
    records.append(created)
    return created


INFO_ALERTS: list[InfoAlert] = [
    InfoAlert(
        id="inf-001",
        title="Mandatory evacuation expanded for river corridor",
        details="Residents within Zone C must leave before 18:30 local time due to rapid flood rise.",
        urgency="extreme urgency alert",
        category="evacuation",
        occurredAt="2026-03-13T16:10:00Z",
        updatedAt="2026-03-13T16:30:00Z",
        area="River Corridor - Zone C",
        source="Regional Emergency Management",
    ),
    InfoAlert(
        id="inf-002",
        title="Bridge closure on Highway 14",
        details="Northbound access is closed. Use East Ridge detour until further notice.",
        urgency="urgent alert",
        category="closure",
        occurredAt="2026-03-13T15:45:00Z",
        updatedAt="2026-03-13T16:05:00Z",
        area="Highway 14",
        source="Transportation Operations Center",
    ),
    InfoAlert(
        id="inf-003",
        title="Traffic congestion near shelter intake",
        details="Expect 25-40 minute delays around Civic Arena access roads.",
        urgency="warning",
        category="traffic",
        occurredAt="2026-03-13T15:40:00Z",
        updatedAt="2026-03-13T15:50:00Z",
        area="Civic Arena",
        source="Traffic Camera Feed",
    ),
]

EVACUATION_PLANS: list[EvacuationPlan] = [
    EvacuationPlan(
        id="plan-001",
        title="Plan 1: Neighbor Pickup + Shelter in Place",
        successProbability=91,
        summary="Coordinate child pickup through trusted neighbors while maintaining safe shelter indoors until verification is complete.",
        steps=[
            "Confirm school release status and current child location.",
            "Notify two nearest trusted neighbors and request pickup support.",
            "Share household safe-word and contact confirmation protocol.",
            "Shelter in place and monitor official alerts every 10 minutes.",
            "Move only after pickup confirmation and route safety check.",
        ],
        packingList=[
            "Family IDs and medication list",
            "Charged phones and battery banks",
            "Water and 24-hour snack kit",
            "Child comfort items and emergency contacts",
        ],
    ),
    EvacuationPlan(
        id="plan-002",
        title="Plan 2: Return via Safe Corridor",
        successProbability=76,
        summary="Use designated low-risk corridor to regroup dependents, then proceed together to the nearest verified shelter.",
        steps=[
            "Verify the corridor is open via traffic and closure alerts.",
            "Travel to pickup point using primary route with backup alternative ready.",
            "Regroup family members and perform a status check.",
            "Proceed to assigned shelter with live route monitoring.",
            "Confirm arrival through family notification channel.",
        ],
        packingList=[
            "Go-bags for each family member",
            "Mask and first-aid basics",
            "Printed emergency contacts",
        ],
    ),
    EvacuationPlan(
        id="plan-003",
        title="Plan 3: Immediate Household Evacuation",
        successProbability=63,
        summary="When local risk escalates quickly, evacuate immediately with predefined meetup and accountability steps.",
        steps=[
            "Trigger evacuation phrase in family group channel.",
            "Collect go-bags and lock utilities if time allows.",
            "Leave via nearest open exit route.",
            "Meet at fallback location if primary shelter is unavailable.",
        ],
        packingList=[
            "IDs, medications, keys",
            "Water, flashlight, blankets",
            "Pet supplies if applicable",
        ],
    ),
]

CONNECTIONS: list[UserConnection] = [
    UserConnection(
        id="conn-001",
        ownerPhone="(555) 010-2030",
        contactPhone="(555) 100-0001",
        relationship="friend",
        trustLevel=2,
        updatedAt="2026-03-13T15:05:00Z",
    )
]

SAVED_INFORMATION: list[SavedInformation] = [
    SavedInformation(
        id="sav-001",
        title="Closest medical shelter",
        note="Westside High School gym includes medical and pet support.",
        updatedAt="2026-03-13T16:15:00Z",
    ),
    SavedInformation(
        id="sav-002",
        title="Family reunification hotline",
        note="1-800-555-0192",
        updatedAt="2026-03-13T15:00:00Z",
    ),
]

WEATHER_UPDATES: list[WeatherUpdate] = [
    WeatherUpdate(
        id="wth-001",
        headline="Wind gusts expected to intensify",
        details="Peak gusts expected 18:00-22:00 local time. Fire spread risk remains elevated.",
        severity="high",
        updatedAt="2026-03-13T16:20:00Z",
    ),
    WeatherUpdate(
        id="wth-002",
        headline="Smoke advisory in effect",
        details="N95 masks recommended outdoors. Reduce prolonged outdoor activity.",
        severity="medium",
        updatedAt="2026-03-13T16:10:00Z",
    ),
]


@router.get("/alerts", response_model=list[InfoAlert])
def list_info_alerts() -> list[InfoAlert]:
    return INFO_ALERTS


@router.get("/evacuation-plans", response_model=list[EvacuationPlan])
def list_evacuation_plans() -> list[EvacuationPlan]:
    return sorted(EVACUATION_PLANS, key=lambda plan: plan.successProbability, reverse=True)


@router.get("/connections", response_model=list[UserConnection])
def list_connections(owner_phone: str | None = Query(default=None)) -> list[UserConnection]:
    if owner_phone is None:
        return CONNECTIONS

    return [connection for connection in CONNECTIONS if connection.ownerPhone == owner_phone]


@router.post("/connections", response_model=ConnectionCreateResponse)
def create_connection(payload: ConnectionCreateRequest) -> ConnectionCreateResponse:
    primary = _upsert_connection(
        records=CONNECTIONS,
        owner_phone=payload.ownerPhone,
        contact_phone=payload.contactPhone,
        relationship=payload.relationship,
    )

    reciprocal = _upsert_connection(
        records=CONNECTIONS,
        owner_phone=payload.contactPhone,
        contact_phone=payload.ownerPhone,
        relationship=RECIPROCAL_RELATIONSHIP[payload.relationship],
    )

    return ConnectionCreateResponse(primary=primary, reciprocal=reciprocal)


@router.get("/saved", response_model=list[SavedInformation])
def list_saved_information() -> list[SavedInformation]:
    return SAVED_INFORMATION


@router.get("/weather", response_model=list[WeatherUpdate])
def list_weather_updates() -> list[WeatherUpdate]:
    return WEATHER_UPDATES
