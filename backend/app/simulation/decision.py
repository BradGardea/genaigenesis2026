"""Simulation-specific LLM decision logic.

Dual mode: uses real watsonx when credentials are configured, otherwise falls
back to a deterministic rule-based engine for dev/demo.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.core.config import settings
from app.simulation.models import AgentDecision, AgentSituation

logger = logging.getLogger(__name__)

# Circuit breaker: skip watsonx after first auth/connection failure
_watsonx_disabled = False

SYSTEM_PROMPT = """\
You are an evacuee in a crisis scenario making survival decisions.
You must respond with ONLY a JSON object — no markdown, no explanation outside the JSON.

Response schema:
{"action": "<depart|wait|reroute|shelter_in_place>", "reasoning": "<brief explanation>", "urgency": <1-10>}

Rules:
- "depart": Start evacuating along your planned route.
- "wait": Stay in place; conditions may improve.
- "reroute": Request a new route (e.g., hazard on current path).
- "shelter_in_place": Take shelter; evacuation is too dangerous.
- urgency: 1=calm, 10=life-threatening emergency.
"""


def _build_user_prompt(situation: AgentSituation) -> str:
    parts = [
        f"Tick {situation.tick}. You are at ({situation.lat:.4f}, {situation.lng:.4f}).",
        f"State: {situation.state.value}.",
        f"Family: {situation.family_size} people, {situation.vehicles} vehicle(s).",
    ]
    if situation.has_children:
        parts.append("You have children with you.")
    if situation.has_elderly:
        parts.append("You have elderly family members.")
    if situation.has_mobility_needs:
        parts.append("Someone in your group has mobility needs.")
    if situation.nearby_hazards:
        parts.append(f"Nearby hazards: {json.dumps(situation.nearby_hazards)}")
    if situation.weather_summary:
        parts.append(f"Weather: {situation.weather_summary}")
    if situation.route_distance_remaining_m is not None:
        parts.append(
            f"Route remaining: {situation.route_distance_remaining_m:.0f}m, "
            f"~{(situation.route_duration_remaining_s or 0):.0f}s"
        )
    if situation.congestion_level > 0:
        parts.append(f"Congestion level: {situation.congestion_level:.1%}")
    return " ".join(parts)


def _rule_based_decision(situation: AgentSituation) -> AgentDecision:
    """Deterministic fallback when watsonx is unavailable."""
    # If already evacuating and hazard nearby → reroute
    if situation.state.value == "evacuating" and situation.nearby_hazards:
        return AgentDecision(
            action="reroute",
            reasoning="Hazard detected near current route",
            urgency=8,
        )

    # If idle and hazard is close → depart immediately
    if situation.state.value == "idle" and situation.nearby_hazards:
        return AgentDecision(
            action="depart",
            reasoning="Hazard nearby — evacuating immediately",
            urgency=9,
        )

    # Severe weather → shelter
    if situation.weather_summary and any(
        kw in situation.weather_summary.lower()
        for kw in ("extreme", "tornado", "hurricane", "severe thunderstorm")
    ):
        return AgentDecision(
            action="shelter_in_place",
            reasoning="Severe weather makes evacuation dangerous",
            urgency=7,
        )

    # High congestion → wait
    if situation.congestion_level > 0.8:
        return AgentDecision(
            action="wait",
            reasoning="Roads heavily congested — waiting for conditions to improve",
            urgency=4,
        )

    # Default: depart if idle, otherwise continue
    if situation.state.value == "idle":
        return AgentDecision(
            action="depart", reasoning="No immediate threats — departing", urgency=3
        )

    return AgentDecision(
        action="wait", reasoning="Continuing current plan", urgency=2
    )


def _parse_decision(text: str) -> AgentDecision | None:
    """Try to extract a valid AgentDecision from LLM output."""
    text = text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
        return AgentDecision(
            action=data["action"],
            reasoning=data.get("reasoning", ""),
            urgency=max(1, min(10, int(data.get("urgency", 5)))),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


async def generate_decision(
    situation: AgentSituation,
    model_id: str = "meta-llama/llama-3-3-70b-instruct",
) -> AgentDecision:
    """Generate an evacuation decision for the given situation.

    Uses real watsonx if configured, otherwise falls back to rules.
    """
    global _watsonx_disabled
    if not settings.watsonx_api_key or _watsonx_disabled:
        return _rule_based_decision(situation)

    try:
        from app.providers.watsonx_client import call_watsonx_raw

        user_prompt = _build_user_prompt(situation)
        result_text = await asyncio.wait_for(
            call_watsonx_raw(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model_id=model_id,
                max_tokens=200,
            ),
            timeout=5.0,
        )
        decision = _parse_decision(result_text)
        if decision is None:
            logger.warning("Failed to parse watsonx response: %s", result_text[:200])
            return _rule_based_decision(situation)
        return decision
    except Exception:
        logger.warning("watsonx call failed — disabling for this session, using rules")
        _watsonx_disabled = True
        return _rule_based_decision(situation)
