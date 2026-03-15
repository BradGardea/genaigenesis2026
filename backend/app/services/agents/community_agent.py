"""CommunityGeneratorAgent — generates synthetic community profiles and relationships.

When the simulation scales beyond the 60 people in the community dataset,
this agent generates realistic new residents with names, scenarios, social
connections, and carpool dependencies so that clustering and evacuation
behaviour remain socially coherent at any scale.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any

from pydantic import BaseModel, Field

from app.providers.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ── Output model ──────────────────────────────────────────────────────

class GeneratedPerson(BaseModel):
    person_id: str
    name: str
    seats_available: int = 0
    scenario: str = ""
    current_position: list[float] = Field(default_factory=list)  # [lat, lng]
    connections: list[dict] = Field(default_factory=list)


class CommunityBatch(BaseModel):
    persons: list[GeneratedPerson]


# ── Fallback data pools ──────────────────────────────────────────────

FIRST_NAMES = [
    "James", "Maria", "Carlos", "Fatima", "David", "Amina", "Joseph", "Grace",
    "Daniel", "Sofia", "Samuel", "Lucia", "Emmanuel", "Ana", "Michael", "Rosa",
    "Patrick", "Blessing", "Thomas", "Esther", "Paul", "Martha", "Robert",
    "Sarah", "John", "Rebecca", "Peter", "Ruth", "Andrew", "Mary", "Gabriel",
    "Esperanza", "Victor", "Nadia", "Omar", "Aisha", "Ibrahim", "Zara",
    "Hassan", "Leila", "Felix", "Carmen", "Luis", "Elena", "Marco", "Beatriz",
    "Ricardo", "Isabel", "Diego", "Valentina",
]

LAST_NAMES = [
    "Moreira", "Santos", "Fernandes", "Costa", "Pereira", "Gomes", "Oliveira",
    "Rodrigues", "Silva", "Nunes", "Machado", "Cardoso", "Mendes", "Torres",
    "Diaz", "Lopez", "Martinez", "Garcia", "Hernandez", "Wilson", "Johnson",
    "Brown", "Davis", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
    "White", "Harris", "Clark", "Lewis", "Hall", "Young", "King",
]

SCENARIOS = [
    "Has a car and can offer rides to others in need",
    "Needs a ride to evacuate",
    "Need to make a stop for supplies",
    "Has limited mobility and needs assistance with evacuation",
    "Has health complications",
]

SCENARIO_WEIGHTS = [0.25, 0.25, 0.18, 0.17, 0.15]

RELATIONSHIP_TYPES = ["dependent", "guardian", "friend", "acquaintance"]


# ── Agent ─────────────────────────────────────────────────────────────

class CommunityGeneratorAgent(BaseAgent[CommunityBatch]):
    agent_name = "community_generator"
    max_tokens = 2000
    temperature = 0.7

    system_prompt = """\
You are a community profile generator for an evacuation simulation in Vilankulo, Mozambique.

Generate realistic resident profiles as a JSON array. Each person needs:
- "person_id": use the provided ID
- "name": realistic name (mix of Portuguese, African, and international names)
- "seats_available": 0 if they need a ride, 1-3 if they have a car
- "scenario": one of: "Has a car and can offer rides to others in need", \
"Needs a ride to evacuate", "Need to make a stop for supplies", \
"Has limited mobility and needs assistance with evacuation", "Has health complications"
- "connections": list of {"target_person_id": "<id>", "relationship": "<type>"} \
where type is dependent, guardian, friend, or acquaintance

Rules:
- ~30% should have cars (seats_available > 0), ~70% need rides
- Create dependent/guardian pairs (families traveling together)
- Each person should have 2-5 connections
- People with "limited mobility" or "health complications" should have at least one guardian connection

Return ONLY a JSON object: {"persons": [...]}
"""

    def build_user_prompt(self, context: dict) -> str:
        count = context["count"]
        start_index = context["start_index"]
        existing_ids = context.get("existing_ids", [])
        bbox = context.get("bbox", {})

        ids = [f"p-{start_index + i:03d}" for i in range(count)]

        parts = [
            f"Generate {count} new community members with IDs: {', '.join(ids)}.",
            f"They live in the area bounded by lat [{bbox.get('min_lat', -22.05)}, "
            f"{bbox.get('max_lat', -21.96)}] and lng [{bbox.get('min_lng', 35.27)}, "
            f"{bbox.get('max_lng', 35.33)}].",
        ]
        if existing_ids:
            sample = existing_ids[:10]
            parts.append(
                f"Existing community members they can connect to: {', '.join(sample)} "
                f"(and {len(existing_ids) - len(sample)} others)."
            )
        parts.append(
            "Create family groups: some people should be dependents/guardians of each other. "
            "People needing rides should be connected to someone with a car."
        )
        return " ".join(parts)

    def parse_response(self, raw_text: str) -> CommunityBatch | None:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
            persons = data.get("persons", data) if isinstance(data, dict) else data
            return CommunityBatch(
                persons=[GeneratedPerson(**p) for p in persons]
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("community_generator: parse failed: %s", e)
            return None

    def fallback(self, context: dict) -> CommunityBatch:
        """Deterministic generation when LLM is unavailable."""
        count = context["count"]
        start_index = context["start_index"]
        existing_ids = context.get("existing_ids", [])
        bbox = context.get("bbox", {})
        rnd = random.Random(start_index)

        min_lat = bbox.get("min_lat", -22.05)
        max_lat = bbox.get("max_lat", -21.96)
        min_lng = bbox.get("min_lng", 35.27)
        max_lng = bbox.get("max_lng", 35.33)

        persons: list[GeneratedPerson] = []
        new_ids = [f"p-{start_index + i:03d}" for i in range(count)]
        all_ids = existing_ids + new_ids

        # Pre-assign scenarios with weighted distribution
        for i in range(count):
            pid = new_ids[i]
            first = rnd.choice(FIRST_NAMES)
            last = rnd.choice(LAST_NAMES)
            scenario = rnd.choices(SCENARIOS, weights=SCENARIO_WEIGHTS, k=1)[0]

            has_car = scenario == "Has a car and can offer rides to others in need"
            seats = rnd.randint(1, 3) if has_car else 0

            lat = rnd.uniform(min_lat, max_lat)
            lng = rnd.uniform(min_lng, max_lng)

            persons.append(GeneratedPerson(
                person_id=pid,
                name=f"{first} {last}",
                seats_available=seats,
                scenario=scenario,
                current_position=[lat, lng],
                connections=[],
            ))

        # Build connections
        for i, person in enumerate(persons):
            pid = person.person_id
            num_connections = rnd.randint(2, 5)
            connected: set[str] = set()

            # Vulnerable people get a guardian from someone with a car
            if person.scenario in (
                "Has limited mobility and needs assistance with evacuation",
                "Has health complications",
            ):
                # Find a nearby person with a car
                car_owners = [
                    p for p in persons
                    if p.seats_available > 0 and p.person_id != pid
                ]
                if car_owners:
                    guardian = rnd.choice(car_owners)
                    person.connections.append({
                        "target_person_id": guardian.person_id,
                        "relationship": "guardian",
                    })
                    # Reciprocal dependent
                    guardian.connections.append({
                        "target_person_id": pid,
                        "relationship": "dependent",
                    })
                    connected.add(guardian.person_id)

            # People needing rides get connected to someone with seats
            if person.seats_available == 0 and not connected:
                car_owners = [
                    p for p in persons
                    if p.seats_available > 0 and p.person_id != pid
                    and p.person_id not in connected
                ]
                if car_owners:
                    driver = rnd.choice(car_owners)
                    person.connections.append({
                        "target_person_id": driver.person_id,
                        "relationship": "dependent",
                    })
                    driver.connections.append({
                        "target_person_id": pid,
                        "relationship": "guardian",
                    })
                    connected.add(driver.person_id)

            # Fill remaining connections with friends/acquaintances
            pool = [p for p in all_ids if p != pid and p not in connected]
            remaining = max(0, num_connections - len(connected))
            if pool and remaining > 0:
                targets = rnd.sample(pool, min(remaining, len(pool)))
                for tid in targets:
                    rel = rnd.choice(["friend", "acquaintance"])
                    person.connections.append({
                        "target_person_id": tid,
                        "relationship": rel,
                    })

        return CommunityBatch(persons=persons)


async def generate_community_batch(
    count: int,
    start_index: int,
    existing_ids: list[str],
    bbox: dict[str, float],
) -> list[dict]:
    """Generate a batch of synthetic community members.

    Returns list of person dicts matching the community data schema.
    """
    agent = CommunityGeneratorAgent()
    result = await agent.run({
        "count": min(count, 20),  # LLM handles up to 20 at a time
        "start_index": start_index,
        "existing_ids": existing_ids,
        "bbox": bbox,
    })
    return [p.model_dump() for p in result.persons]
