"""Decision agent — orchestrates other agents and chooses a route for the user.

Gathers route matrix, hazard assessment, and weather briefing in parallel,
then uses the LLM (or heuristic fallback) to make a personalized evacuation
decision based on the user's circumstances.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from app.providers.base_agent import BaseAgent
from app.schemas.agent_models import (
    AgentBriefingRequest,
    AgentBriefingResponse,
    DecisionOutput,
    DecisionRequest,
    HazardAnalystOutput,
    MeteorologistOutput,
    RouteCandidateOutput,
    RouteMatrixRequest,
    RoutingAnalystOutput,
)
from app.services.agents.hazard_analyst_agent import generate_hazard_briefing
from app.services.agents.meteorologist_agent import generate_meteorologist_briefing
from app.services.agents.routing_agent import generate_route_matrix

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an emergency evacuation decision advisor. Given a person's \
circumstances, available route options, hazard conditions, and weather, \
you must recommend a concrete action.

Consider:
- Family composition (children, elderly, mobility needs) affects departure urgency
- Vehicle availability affects route viability
- Supply levels affect how long they can shelter
- Medical needs increase urgency
- Pets require additional preparation time
- Hazard proximity and severity
- Weather conditions along each route
- Route duration relative to the household's capabilities

You must respond with ONLY a JSON object — no markdown, no extra text.

Response schema:
{
  "action": "<evacuate_now|evacuate_soon|shelter_in_place|monitor>",
  "chosen_route": "<label of best route for this person>",
  "departure_window": "<immediately|within_1h|within_4h|not_yet>",
  "urgency": <1-10>,
  "reasoning": "<2-3 sentences explaining the decision>",
  "preparation_steps": ["<step1>", "<step2>", ...],
  "warnings": ["<warning1>", ...],
  "confidence": "<high|medium|low>",
  "hazard_summary": "<1 sentence>",
  "weather_summary": "<1 sentence>"
}
"""


class DecisionAgent(BaseAgent[DecisionOutput]):
    agent_name = "decision"
    system_prompt = SYSTEM_PROMPT
    max_tokens = 800

    def build_user_prompt(self, context: dict) -> str:
        parts: list[str] = []

        # Personal circumstances
        circ = context.get("circumstances", {})
        parts.append("=== YOUR CIRCUMSTANCES ===")
        parts.append(f"Family size: {circ.get('family_size', 1)}")
        parts.append(f"Vehicles: {circ.get('vehicles', 1)}")
        flags = []
        if circ.get("has_children"):
            flags.append("children present")
        if circ.get("has_elderly"):
            flags.append("elderly members")
        if circ.get("has_mobility_needs"):
            flags.append("mobility-impaired members")
        if circ.get("medical_needs"):
            flags.append("ongoing medical needs")
        if circ.get("pets"):
            flags.append("pets to transport")
        if flags:
            parts.append(f"Special factors: {', '.join(flags)}")
        parts.append(f"Supplies on hand: ~{circ.get('supplies_hours', 24):.0f} hours")
        parts.append("")

        # Route candidates
        routing: RoutingAnalystOutput | None = context.get("routing_output")
        if routing:
            parts.append(f"=== ROUTE OPTIONS ({len(routing.candidates)}) ===")
            parts.append(f"Routing analyst says: {routing.summary}")
            parts.append(f"Recommended by analyst: {routing.recommended_route}")
            parts.append(f"Evacuation urgency: {routing.evacuation_urgency}")
            parts.append("")
            for c in routing.candidates:
                parts.append(
                    f"- {c.label}: {c.distance_meters:.0f}m, {c.duration_seconds:.0f}s, "
                    f"score={c.feasibility_score}, hazard={c.hazard_exposure}, "
                    f"weather={c.weather_impact}"
                )
                if c.hazards_crossed:
                    parts.append(f"  Hazards crossed: {c.hazards_crossed}")
                if c.weather_risks:
                    parts.append(f"  Weather risks: {c.weather_risks}")
            parts.append("")

        # Hazard conditions
        hazard: HazardAnalystOutput | None = context.get("hazard_output")
        if hazard:
            parts.append("=== HAZARD CONDITIONS ===")
            parts.append(f"Wildfire risk: {hazard.wildfire_risk}")
            parts.append(f"Flood risk: {hazard.flood_risk}")
            parts.append(f"Severe weather risk: {hazard.severe_weather_risk}")
            parts.append(f"Active hazard zones: {hazard.active_hazard_zones}")
            parts.append(f"Evacuation recommended: {hazard.evacuation_recommended}")
            parts.append(f"Assessment: {hazard.summary}")
            parts.append("")

        # Weather conditions
        weather: MeteorologistOutput | None = context.get("weather_output")
        if weather:
            parts.append("=== WEATHER CONDITIONS ===")
            parts.append(f"Risk level: {weather.risk_level}")
            parts.append(f"Key threats: {weather.key_threats}")
            parts.append(f"Forecast: {weather.forecast_outlook}")
            parts.append(f"Assessment: {weather.summary}")

        return "\n".join(parts)

    def parse_response(self, raw_text: str) -> DecisionOutput | None:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)

            # Resolve geometry from the chosen route label
            chosen_label = data.get("chosen_route", "")
            geometry = {}
            distance = 0.0
            duration = 0.0
            routing: RoutingAnalystOutput | None = self._routing_output
            if routing:
                for c in routing.candidates:
                    if c.label == chosen_label:
                        geometry = c.geometry
                        distance = c.distance_meters
                        duration = c.duration_seconds
                        break
                # If LLM returned a label that doesn't match, pick the analyst's recommendation
                if not geometry and routing.candidates:
                    for c in routing.candidates:
                        if c.label == routing.recommended_route:
                            geometry = c.geometry
                            distance = c.distance_meters
                            duration = c.duration_seconds
                            chosen_label = c.label
                            break

            return DecisionOutput(
                action=data.get("action", "monitor"),
                chosen_route=chosen_label,
                chosen_route_geometry=geometry,
                chosen_route_distance_meters=distance,
                chosen_route_duration_seconds=duration,
                departure_window=data.get("departure_window", "not_yet"),
                urgency=max(1, min(10, int(data.get("urgency", 5)))),
                reasoning=data.get("reasoning", ""),
                preparation_steps=data.get("preparation_steps", []),
                warnings=data.get("warnings", []),
                confidence=data.get("confidence", "medium"),
                hazard_summary=data.get("hazard_summary", ""),
                weather_summary=data.get("weather_summary", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    def fallback(self, context: dict) -> DecisionOutput:
        circ = context.get("circumstances", {})
        routing: RoutingAnalystOutput | None = context.get("routing_output")
        hazard: HazardAnalystOutput | None = context.get("hazard_output")
        weather: MeteorologistOutput | None = context.get("weather_output")

        # ── Determine action from conditions ─────────────────────

        # Start with routing analyst's urgency
        evac_urgency = "low"
        if routing:
            evac_urgency = routing.evacuation_urgency

        hazard_recommends_evac = hazard.evacuation_recommended if hazard else False
        weather_risk = weather.risk_level if weather else "low"

        # Vulnerability multiplier based on circumstances
        vulnerability = 0
        if circ.get("has_children"):
            vulnerability += 1
        if circ.get("has_elderly"):
            vulnerability += 2
        if circ.get("has_mobility_needs"):
            vulnerability += 2
        if circ.get("medical_needs"):
            vulnerability += 2
        if circ.get("vehicles", 1) == 0:
            vulnerability += 3

        supplies_hours = circ.get("supplies_hours", 24)

        # Decide action
        if hazard_recommends_evac and evac_urgency in ("high", "critical"):
            action = "evacuate_now"
            departure_window = "immediately"
            urgency = min(10, 8 + vulnerability)
        elif hazard_recommends_evac or evac_urgency in ("high", "critical"):
            action = "evacuate_now" if vulnerability >= 3 else "evacuate_soon"
            departure_window = "immediately" if vulnerability >= 3 else "within_1h"
            urgency = min(10, 7 + vulnerability)
        elif evac_urgency == "medium" or weather_risk in ("high", "extreme"):
            if vulnerability >= 2 or supplies_hours < 12:
                action = "evacuate_soon"
                departure_window = "within_1h"
                urgency = min(10, 6 + vulnerability)
            else:
                action = "monitor"
                departure_window = "within_4h"
                urgency = 4
        elif weather_risk == "medium":
            action = "monitor"
            departure_window = "not_yet"
            urgency = 3
        else:
            action = "monitor"
            departure_window = "not_yet"
            urgency = 2

        # Override: if supplies are very low, escalate
        if supplies_hours < 6 and action == "monitor":
            action = "evacuate_soon"
            departure_window = "within_1h"
            urgency = max(urgency, 6)

        # Override: severe weather makes roads impassable → shelter
        if weather_risk == "extreme" and evac_urgency != "critical":
            if all(
                c.weather_impact == "high"
                for c in (routing.candidates if routing else [])
            ):
                action = "shelter_in_place"
                departure_window = "not_yet"
                urgency = max(urgency, 7)

        # ── Choose route ─────────────────────────────────────────

        chosen_label = ""
        chosen_geometry: dict = {}
        chosen_distance = 0.0
        chosen_duration = 0.0

        if routing and routing.candidates:
            # Adjust candidate scores for personal circumstances
            best = None
            best_score = -1.0
            for c in routing.candidates:
                score = c.feasibility_score

                # Penalize long routes for vulnerable groups
                if vulnerability >= 2 and c.duration_seconds > 3600:
                    score -= 10
                if circ.get("has_elderly") and c.duration_seconds > 5400:
                    score -= 15

                # Penalize weather-impacted routes when transporting children/elderly
                if c.weather_impact in ("medium", "high") and (
                    circ.get("has_children") or circ.get("has_elderly")
                ):
                    score -= 10

                # Penalize routes crossing hazards more heavily for vulnerable groups
                if c.hazards_crossed and vulnerability >= 2:
                    score -= len(c.hazards_crossed) * 10

                # No vehicle → can't take long routes
                if circ.get("vehicles", 1) == 0 and c.distance_meters > 10000:
                    score -= 30

                # Bonus for shorter/faster routes when mobility-impaired
                if circ.get("has_mobility_needs") and c.hazard_exposure == "none":
                    score += 5

                if score > best_score:
                    best_score = score
                    best = c

            if best:
                chosen_label = best.label
                chosen_geometry = best.geometry
                chosen_distance = best.distance_meters
                chosen_duration = best.duration_seconds

        # ── Build preparation steps ──────────────────────────────

        preparation_steps: list[str] = []
        if action in ("evacuate_now", "evacuate_soon"):
            preparation_steps.append("Gather essential documents (IDs, insurance papers)")
            preparation_steps.append("Pack water and non-perishable food")
            if circ.get("medical_needs"):
                preparation_steps.append("Ensure all medications and medical supplies are packed")
            if circ.get("has_children"):
                preparation_steps.append("Pack child essentials (diapers, formula, comfort items)")
            if circ.get("has_elderly"):
                preparation_steps.append("Assist elderly members and ensure mobility aids are ready")
            if circ.get("pets"):
                preparation_steps.append("Prepare pet carriers, food, and vaccination records")
            if circ.get("has_mobility_needs"):
                preparation_steps.append("Ensure wheelchair/mobility equipment is loaded first")
            preparation_steps.append("Charge all phones and portable batteries")
            preparation_steps.append("Fill vehicle fuel tanks if possible")
        elif action == "shelter_in_place":
            preparation_steps.append("Move to interior room away from windows")
            preparation_steps.append("Fill bathtubs and containers with water")
            preparation_steps.append("Gather flashlights, batteries, and first aid kit")
            if circ.get("medical_needs"):
                preparation_steps.append("Keep medications accessible")
        else:
            preparation_steps.append("Stay informed via local emergency broadcasts")
            preparation_steps.append("Prepare a go-bag in case conditions change")

        # ── Build warnings ───────────────────────────────────────

        warnings: list[str] = []
        if circ.get("vehicles", 1) == 0:
            warnings.append("No vehicle available — coordinate with neighbors or call emergency transport")
        if supplies_hours < 12:
            warnings.append(f"Low supplies (~{supplies_hours:.0f}h) — prioritize departure")
        if vulnerability >= 3:
            warnings.append("High-vulnerability household — earlier departure strongly recommended")
        if routing and all(len(c.hazards_crossed) > 0 for c in routing.candidates):
            warnings.append("All available routes cross at least one hazard zone")
        if weather_risk in ("high", "extreme"):
            warnings.append(f"Weather risk is {weather_risk} — road conditions may deteriorate")

        # ── Build reasoning ──────────────────────────────────────

        reasoning_parts: list[str] = []
        if action == "evacuate_now":
            reasoning_parts.append("Conditions require immediate evacuation.")
        elif action == "evacuate_soon":
            reasoning_parts.append("Evacuation is recommended within the next hour.")
        elif action == "shelter_in_place":
            reasoning_parts.append("Road conditions make evacuation too dangerous right now.")
        else:
            reasoning_parts.append("Conditions are being monitored; no immediate evacuation needed.")

        if chosen_label:
            reasoning_parts.append(
                f"The '{chosen_label}' route is recommended "
                f"({chosen_distance / 1000:.1f} km, ~{chosen_duration / 60:.0f} min)."
            )
        if vulnerability >= 2:
            reasoning_parts.append(
                "Special accommodation for vulnerable household members factored into route selection."
            )

        # Confidence
        if routing and hazard and weather:
            confidence = "high"
        elif routing:
            confidence = "medium"
        else:
            confidence = "low"

        return DecisionOutput(
            action=action,
            chosen_route=chosen_label,
            chosen_route_geometry=chosen_geometry,
            chosen_route_distance_meters=chosen_distance,
            chosen_route_duration_seconds=chosen_duration,
            departure_window=departure_window,
            urgency=min(10, urgency),
            reasoning=" ".join(reasoning_parts),
            preparation_steps=preparation_steps,
            warnings=warnings,
            confidence=confidence,
            hazard_summary=hazard.summary if hazard else "Hazard data unavailable.",
            weather_summary=weather.summary if weather else "Weather data unavailable.",
        )

    async def run(self, context: dict) -> DecisionOutput:
        self._routing_output = context.get("routing_output")
        return await super().run(context)


# ── Service function ─────────────────────────────────────────────────

async def generate_decision(request: DecisionRequest) -> AgentBriefingResponse:
    """Orchestrate sub-agents and produce a personalized evacuation decision."""

    # Build sub-agent requests
    route_req = RouteMatrixRequest(
        origin_lat=request.origin_lat,
        origin_lng=request.origin_lng,
        destination_lat=request.destination_lat,
        destination_lng=request.destination_lng,
        max_alternatives=request.max_alternatives,
    )
    briefing_req = AgentBriefingRequest(
        latitude=request.origin_lat,
        longitude=request.origin_lng,
    )

    # Run all three sub-agents in parallel
    routing_task = asyncio.create_task(generate_route_matrix(route_req))
    hazard_task = asyncio.create_task(generate_hazard_briefing(briefing_req))
    weather_task = asyncio.create_task(generate_meteorologist_briefing(briefing_req))

    routing_resp, hazard_resp, weather_resp = await asyncio.gather(
        routing_task, hazard_task, weather_task, return_exceptions=True,
    )

    # Extract structured outputs from envelope responses
    routing_output = None
    if isinstance(routing_resp, AgentBriefingResponse) and routing_resp.structured_data:
        try:
            routing_output = RoutingAnalystOutput(**routing_resp.structured_data)
        except Exception:
            logger.warning("Failed to parse routing output")

    hazard_output = None
    if isinstance(hazard_resp, AgentBriefingResponse) and hazard_resp.structured_data:
        try:
            hazard_output = HazardAnalystOutput(**hazard_resp.structured_data)
        except Exception:
            logger.warning("Failed to parse hazard output")

    weather_output = None
    if isinstance(weather_resp, AgentBriefingResponse) and weather_resp.structured_data:
        try:
            weather_output = MeteorologistOutput(**weather_resp.structured_data)
        except Exception:
            logger.warning("Failed to parse weather output")

    context = {
        "circumstances": {
            "family_size": request.family_size,
            "vehicles": request.vehicles,
            "has_children": request.has_children,
            "has_elderly": request.has_elderly,
            "has_mobility_needs": request.has_mobility_needs,
            "supplies_hours": request.supplies_hours,
            "medical_needs": request.medical_needs,
            "pets": request.pets,
        },
        "routing_output": routing_output,
        "hazard_output": hazard_output,
        "weather_output": weather_output,
    }

    agent = DecisionAgent()
    output = await agent.run(context)

    # Determine overall status
    from app.core.config import settings
    import app.providers.watsonx_client as _mod

    if not settings.watsonx_api_key or _mod._watsonx_disabled:
        status = "fallback"
    else:
        status = "ok"

    # Collect data sources from all sub-agents
    data_sources: set[str] = set()
    for resp in (routing_resp, hazard_resp, weather_resp):
        if isinstance(resp, AgentBriefingResponse):
            data_sources.update(resp.data_sources)

    return AgentBriefingResponse(
        agent_type="decision",
        status=status,
        briefing=output.reasoning,
        structured_data=output.model_dump(),
        data_sources=sorted(data_sources),
        generated_at=datetime.utcnow(),
    )
