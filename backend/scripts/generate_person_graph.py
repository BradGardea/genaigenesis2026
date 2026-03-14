from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

RelationshipType = Literal["dependent", "guardian", "friend", "acquaintance"]


# Basic American-style name lists to keep generation offline and deterministic.
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Melissa", "George", "Deborah",
    "Timothy", "Stephanie", "Jason", "Rebecca", "Jeffrey", "Sharon", "Ryan", "Laura",
    "Jacob", "Cynthia", "Gary", "Kathleen", "Nicholas", "Amy", "Eric", "Shirley",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
    "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell",
    "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
    "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales",
]

RELATIONSHIP_TYPES: tuple[RelationshipType, ...] = (
    "dependent",
    "guardian",
    "friend",
    "acquaintance",
)

BASE_LON = 29.222
BASE_LAT = -1.679
PERSON_SCENARIO = "Severe storm evacuation support network"
PERSON_SCENARIOS = [
    "Severe storm evacuation support network",
    "Volcanic ash avoidance and mutual aid",
    "Flooded roads rideshare coordination",
    "Power outage welfare checks and pooling",
    "Wildfire smoke relocation carpool",
]


def unique_name(existing: set[str]) -> str:
    """Generate a unique full name from the provided lists."""
    while True:
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in existing:
            existing.add(name)
            return name


def random_seats_available() -> int:
    # Range 0-8 open seats (excludes driver); biased toward smaller counts.
    return max(0, int(random.triangular(0, 8, 2)))


def random_position() -> tuple[float, float]:
    # Small jitter around the Goma coordinate to keep people clustered.
    lon = BASE_LON + random.uniform(-0.025, 0.025)
    lat = BASE_LAT + random.uniform(-0.025, 0.025)
    return (round(lon, 6), round(lat, 6))


def build_people(count: int) -> list[dict[str, Any]]:
    names: set[str] = set()
    people: list[dict[str, Any]] = []

    for idx in range(count):
        person_id = f"p-{idx+1:03d}"
        name = unique_name(names)
        people.append(
            {
                "person_id": person_id,
                "name": name,
                "seats_available": random_seats_available(),
                "scenario": random.choice(PERSON_SCENARIOS),
                "current_position": list(random_position()),
                "connections": [],  # filled later
            }
        )
    return people


def connect_people(people: list[dict[str, Any]], min_degree: int, max_degree: int) -> None:
    by_id = {p["person_id"]: p for p in people}

    for person in people:
        desired_degree = random.randint(min_degree, max_degree)
        possible_targets = [p for p in people if p["person_id"] != person["person_id"]]

        # Avoid duplicates while sampling.
        targets = random.sample(possible_targets, k=min(desired_degree, len(possible_targets)))
        seen_targets: set[str] = set()

        for target in targets:
            target_id = target["person_id"]
            if target_id in seen_targets:
                continue
            seen_targets.add(target_id)
            relation = random.choice(RELATIONSHIP_TYPES)
            person["connections"].append(
                {"target_person_id": target_id, "relationship": relation}
            )

            # Optionally create reciprocal link for better connectivity.
            if random.random() < 0.55:
                reverse_relation = random.choice(RELATIONSHIP_TYPES)
                reverse_person = by_id[target_id]
                # Prevent duplicate reverse edges.
                if not any(c["target_person_id"] == person["person_id"] for c in reverse_person["connections"]):
                    reverse_person["connections"].append(
                        {"target_person_id": person["person_id"], "relationship": reverse_relation}
                    )


def build_payload(
    count: int,
    min_degree: int,
    max_degree: int,
    seed: int,
) -> dict[str, Any]:
    random.seed(seed)
    people = build_people(count)
    connect_people(people, min_degree=min_degree, max_degree=max_degree)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "dataset_name": "goma_community_relationships_mock",
        "version": "2.0",
        "generated_at": generated_at,
        "scenario_note": (
            "Algorithmically generated many-to-many social connections for evacuation "
            "and carpool planning near Goma, DR Congo, using American-style names."
        ),
        "scenario": "Severe storm evacuation support network",
        "location": {
            "name": "Goma, DR Congo",
            "latitude": BASE_LAT,
            "longitude": BASE_LON,
            "timezone": "Africa/Lubumbashi",
        },
        "schema_alignment": {
            "person_schema_base": "PersonWithConnections / PersonConnectionsResponse",
            "relationship_types": list(RELATIONSHIP_TYPES),
            "position_format": "tuple [longitude, latitude] in decimal degrees",
        },
        "persons": people,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mock person-to-person relationship graph.")
    parser.add_argument("--count", type=int, default=60, help="Number of people to generate.")
    parser.add_argument("--min-degree", type=int, default=3, help="Minimum connections per person.")
    parser.add_argument("--max-degree", type=int, default=7, help="Maximum connections per person.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument(
        "--outfile",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "goma_community_relationships_mock.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()

    payload = build_payload(
        count=args.count,
        min_degree=args.min_degree,
        max_degree=args.max_degree,
        seed=args.seed,
    )
    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    with args.outfile.open("w", encoding="utf-8") as sink:
        json.dump(payload, sink, ensure_ascii=False, indent=2)
    print(f"Generated {len(payload['persons'])} people to {args.outfile}")


if __name__ == "__main__":
    main()
