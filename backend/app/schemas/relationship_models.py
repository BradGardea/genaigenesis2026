from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RelationshipType = Literal["dependent", "guardian", "friend", "acquaintance"]


class PersonConnection(BaseModel):
    target_person_id: str = Field(..., description="Unique identifier of the connected person")
    relationship: RelationshipType


class PersonSummary(BaseModel):
    person_id: str
    name: str
    seats_available: int = Field(..., ge=0, description="Number of open passenger seats available")
    scenario: str = Field(..., description="Scenario label applicable to this person")
    current_position: tuple[float, float] = Field(
        ..., description="(longitude, latitude) tuple in decimal degrees"
    )


class PersonWithConnections(PersonSummary):
    connections: list[PersonConnection]


class PersonGraphMetadata(BaseModel):
    dataset_name: str
    version: str
    generated_at: str
    scenario_note: str
    scenario: str
    location: dict[str, Any]
    schema_alignment: dict[str, Any]


class PersonConnectionNode(BaseModel):
    relationship: RelationshipType
    person: PersonSummary


class PersonConnectionsResponse(BaseModel):
    metadata: PersonGraphMetadata
    focal_person: PersonWithConnections
    connections: list[PersonConnectionNode]
