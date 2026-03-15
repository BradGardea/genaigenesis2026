from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.relationship_models import (
    ConnectionEmergencyEvent,
    HelpNeededConnectionsResponse,
    PersonConnectionNode,
    PersonConnectionsResponse,
    PersonGraphMetadata,
    PersonSummary,
    PersonWithConnections,
)

PERSON_GRAPH_FILENAME = "goma_community_relationships_mock.json"
HELP_NEEDED_SCENARIO = "needs a ride to evacuate"
EMERGENCY_ACTIVATION_STEP = 5


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


def _is_help_needed_candidate(person: PersonWithConnections) -> bool:
    return person.scenario.strip().lower() == HELP_NEEDED_SCENARIO


def _active_emergency_target_id(person: PersonWithConnections, step_index: int) -> str | None:
    if step_index < EMERGENCY_ACTIVATION_STEP:
        return None

    people_by_id = _people_index()
    for connection in person.connections:
        target = people_by_id.get(connection.target_person_id)
        if target and _is_help_needed_candidate(target):
            return target.person_id

    return None


def _connection_nodes(person: PersonWithConnections, step_index: int) -> list[PersonConnectionNode]:
    people_by_id = _people_index()
    nodes: list[PersonConnectionNode] = []
    active_emergency_target_id = _active_emergency_target_id(person, step_index)

    for connection in person.connections:
        target = people_by_id.get(connection.target_person_id)
        if not target:
            # Skip silently if dataset refers to a missing person to avoid hard failures.
            continue
        emergency_event = None
        if target.person_id == active_emergency_target_id:
            emergency_event = ConnectionEmergencyEvent(
                event_type="needs_help",
                active=True,
                activated_at_step=EMERGENCY_ACTIVATION_STEP,
                title=f"{target.name} needs help",
                detail=(
                    f"{target.name} needs evacuation assistance. "
                    f"Scenario: {target.scenario}."
                ),
            )
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
                emergency_event=emergency_event,
            )
        )
    return nodes


async def get_person_connections(person_ref: str, step_index: int = 0) -> PersonConnectionsResponse:
    """Return a focal person and their connected people with relationship labels."""

    focal_person = _resolve_person(person_ref)
    return PersonConnectionsResponse(
        step_index=step_index,
        metadata=_metadata_model(),
        focal_person=focal_person,
        connections=_connection_nodes(focal_person, step_index),
    )


async def get_help_needed_connections(
    person_ref: str,
    step_index: int = 0,
) -> HelpNeededConnectionsResponse:
    focal_person = _resolve_person(person_ref)
    connection_nodes = _connection_nodes(focal_person, step_index)
    return HelpNeededConnectionsResponse(
        step_index=step_index,
        focal_person=PersonSummary(
            person_id=focal_person.person_id,
            name=focal_person.name,
            seats_available=focal_person.seats_available,
            scenario=focal_person.scenario,
            current_position=focal_person.current_position,
        ),
        help_needed=[
            node for node in connection_nodes if node.emergency_event and node.emergency_event.active
        ],
    )


async def get_first_person_connections(step_index: int = 0) -> PersonConnectionsResponse:
    """Convenience helper: return the first person in the dataset and their connections."""

    payload = _graph_payload()
    persons = payload.get("persons", [])
    if not persons:
        raise ValueError("No persons available in the dataset.")

    first_person_id = persons[0].get("person_id")
    if not first_person_id:
        raise ValueError("First person entry is missing 'person_id'.")

    return await get_person_connections(first_person_id, step_index)


async def get_first_person_help_needed(step_index: int = 0) -> HelpNeededConnectionsResponse:
    payload = _graph_payload()
    persons = payload.get("persons", [])
    if not persons:
        raise ValueError("No persons available in the dataset.")

    first_person_id = persons[0].get("person_id")
    if not first_person_id:
        raise ValueError("First person entry is missing 'person_id'.")

    return await get_help_needed_connections(first_person_id, step_index)
