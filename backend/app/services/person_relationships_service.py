from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.relationship_models import (
    PersonConnectionNode,
    PersonConnectionsResponse,
    PersonGraphMetadata,
    PersonSummary,
    PersonWithConnections,
)

PERSON_GRAPH_FILENAME = "goma_community_relationships_mock.json"


def _root_path() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _graph_payload() -> dict[str, Any]:
    file_path = _root_path() / "data" / PERSON_GRAPH_FILENAME
    with file_path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if "persons" not in payload or not isinstance(payload["persons"], list):
        raise ValueError("Person graph dataset must include a 'persons' list.")
    return payload


@lru_cache(maxsize=1)
def _people_index() -> dict[str, PersonWithConnections]:
    payload = _graph_payload()
    people = [PersonWithConnections(**person) for person in payload["persons"]]
    return {person.person_id: person for person in people}


@lru_cache(maxsize=1)
def _people_by_name() -> dict[str, PersonWithConnections]:
    return {person.name.lower(): person for person in _people_index().values()}


def _metadata_model() -> PersonGraphMetadata:
    metadata = {key: value for key, value in _graph_payload().items() if key != "persons"}
    return PersonGraphMetadata(
        dataset_name=str(metadata.get("dataset_name", PERSON_GRAPH_FILENAME)),
        version=str(metadata.get("version", "unknown")),
        generated_at=str(metadata.get("generated_at", "")),
        scenario_note=str(metadata.get("scenario_note", "")),
        scenario=str(metadata.get("scenario", "")),
        location=metadata.get("location", {}),
        schema_alignment=metadata.get("schema_alignment", {}),
    )


def _resolve_person(person_ref: str) -> PersonWithConnections:
    people_by_id = _people_index()
    people_by_name = _people_by_name()

    if person_ref in people_by_id:
        return people_by_id[person_ref]

    normalized = person_ref.strip().lower()
    if normalized in people_by_name:
        return people_by_name[normalized]

    raise KeyError(f"Person '{person_ref}' not found in the dataset.")


def _connection_nodes(person: PersonWithConnections) -> list[PersonConnectionNode]:
    people_by_id = _people_index()
    nodes: list[PersonConnectionNode] = []

    for connection in person.connections:
        target = people_by_id.get(connection.target_person_id)
        if not target:
            # Skip silently if dataset refers to a missing person to avoid hard failures.
            continue
        nodes.append(
            PersonConnectionNode(
                relationship=connection.relationship,
                person=PersonSummary(
                    person_id=target.person_id,
                    name=target.name,
                    seats_available=target.seats_available,
                    scenario=target.scenario,
                    current_position=target.current_position,
                ),
            )
        )
    return nodes


async def get_person_connections(person_ref: str) -> PersonConnectionsResponse:
    """Return a focal person and their connected people with relationship labels."""

    focal_person = _resolve_person(person_ref)
    return PersonConnectionsResponse(
        metadata=_metadata_model(),
        focal_person=focal_person,
        connections=_connection_nodes(focal_person),
    )


async def get_first_person_connections() -> PersonConnectionsResponse:
    """Convenience helper: return the first person in the dataset and their connections."""

    payload = _graph_payload()
    persons = payload.get("persons", [])
    if not persons:
        raise ValueError("No persons available in the dataset.")

    first_person_id = persons[0].get("person_id")
    if not first_person_id:
        raise ValueError("First person entry is missing 'person_id'.")

    return await get_person_connections(first_person_id)
