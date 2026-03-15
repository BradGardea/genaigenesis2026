"""Routing analyst agent — evaluates multiple route candidates against hazards and weather."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import uuid
from datetime import datetime

from shapely.geometry import LineString, shape

from app.models.routing import Coordinate
from app.providers.base_agent import BaseAgent
from app.schemas.agent_models import (
    AgentBriefingResponse,
    RouteCandidateOutput,
    RouteMatrixRequest,
    RoutingAnalystOutput,
)
from app.services import alerts_service, forecasts_service
from app.services.hazard_store import hazard_store
from app.services.mapbox_routing import (
    CRISIS_TRAFFIC_FACTOR,
    _route_intersects_hazards,
    _select_best_route,
    fetch_route,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a crisis routing analyst. Given multiple route candidates with their \
hazard exposure and weather conditions, produce a feasibility assessment.

You must respond with ONLY a JSON object — no markdown, no extra text.

Response schema:
{
  "summary": "<2-3 sentence overview of routing situation>",
  "recommended_route": "<label of best route>",
  "candidate_assessments": [
    {
      "label": "<route label>",
      "feasibility_score": <0-100>,
      "hazard_exposure": "<none|low|medium|high>",
      "weather_impact": "<none|low|medium|high>",
      "reasoning": "<why this score>"
    }
  ],
  "overall_assessment": "<overall evacuation routing situation>",
  "evacuation_urgency": "<low|medium|high|critical>"
}
"""


# ── Helpers for generating alternative waypoints ─────────────────────

def _midpoint(lat1: float, lng1: float, lat2: float, lng2: float) -> tuple[float, float]:
    return ((lat1 + lat2) / 2, (lng1 + lng2) / 2)


def _offset_waypoint(
    mid_lat: float, mid_lng: float,
    bearing_deg: float, offset_deg: float,
) -> Coordinate:
    """Push a point in a compass direction by offset_deg."""
    rad = math.radians(bearing_deg)
    return Coordinate(
        lat=round(mid_lat + offset_deg * math.cos(rad), 6),
        lng=round(mid_lng + offset_deg * math.sin(rad), 6),
    )


def _generate_alternative_waypoints(
    origin: Coordinate, destination: Coordinate, count: int = 3,
) -> list[tuple[str, list[Coordinate]]]:
    """Generate named waypoint sets that push the route in different directions.

    Returns list of (label, [waypoints]) tuples. The first is always the
    direct route (no waypoints).
    """
    mid_lat, mid_lng = _midpoint(origin.lat, origin.lng, destination.lat, destination.lng)
    dx = destination.lng - origin.lng
    dy = destination.lat - origin.lat
    route_len_deg = math.hypot(dx, dy)
    offset = max(route_len_deg * 0.15, 0.02)  # 15% of route length, min ~2 km

    # Perpendicular bearing to origin→destination line
    base_bearing = math.degrees(math.atan2(dx, dy))
    perp_left = (base_bearing - 90) % 360
    perp_right = (base_bearing + 90) % 360

    alternatives: list[tuple[str, list[Coordinate]]] = [
        ("Direct route", []),
    ]

    labels_bearings = [
        ("Northern bypass", perp_left if perp_left < 180 else perp_right),
        ("Southern bypass", perp_right if perp_right >= 180 else perp_left),
        ("Wide northern bypass", perp_left if perp_left < 180 else perp_right),
        ("Wide southern bypass", perp_right if perp_right >= 180 else perp_left),
    ]

    for i, (label, bearing) in enumerate(labels_bearings[: count - 1]):
        scale = offset * (1.5 if "Wide" in label else 1.0)
        wp = _offset_waypoint(mid_lat, mid_lng, bearing, scale)
        alternatives.append((label, [wp]))

    return alternatives


# ── Weather sampling along a route ───────────────────────────────────

async def _sample_weather_along_route(geometry: dict, num_points: int = 3) -> list[dict]:
    """Fetch weather at evenly-spaced points along a route geometry."""
    line = shape(geometry)
    if not isinstance(line, LineString) or line.is_empty:
        return []

    points = []
    for i in range(num_points):
        frac = i / max(num_points - 1, 1)
        pt = line.interpolate(frac, normalized=True)
        points.append((pt.y, pt.x))  # (lat, lon)

    results = []
    for lat, lon in points:
        try:
            forecast = await forecasts_service.get_hourly_forecast(lat, lon)
            hour = forecast.hourly[0] if forecast.hourly else None
            results.append({
                "lat": lat,
                "lng": lon,
                "temperature_c": hour.temperature_c if hour else None,
                "wind_speed_kmh": hour.wind_speed_kmh if hour else None,
                "precipitation_probability": hour.precipitation_probability if hour else None,
            })
        except Exception:
            results.append({"lat": lat, "lng": lon})
    return results


def _assess_weather_risk(weather_points: list[dict]) -> tuple[str, list[str]]:
    """Heuristic weather impact from sampled points. Returns (level, risks)."""
    risks: list[str] = []
    max_wind = 0.0
    max_precip = 0

    for wp in weather_points:
        wind = wp.get("wind_speed_kmh") or 0
        precip = wp.get("precipitation_probability") or 0
        max_wind = max(max_wind, wind)
        max_precip = max(max_precip, precip)

    if max_wind > 80:
        risks.append(f"Dangerous winds ({max_wind:.0f} km/h)")
    elif max_wind > 50:
        risks.append(f"Strong winds ({max_wind:.0f} km/h)")

    if max_precip > 80:
        risks.append(f"Heavy precipitation likely ({max_precip}%)")
    elif max_precip > 50:
        risks.append(f"Moderate precipitation chance ({max_precip}%)")

    if max_wind > 80 or max_precip > 80:
        level = "high"
    elif max_wind > 50 or max_precip > 50:
        level = "medium"
    elif max_wind > 30 or max_precip > 30:
        level = "low"
    else:
        level = "none"

    return level, risks


# ── Route candidate builder ─────────────────────────────────────────

async def _build_candidate(
    label: str,
    origin: Coordinate,
    destination: Coordinate,
    waypoints: list[Coordinate],
    hazard_polygons: list[dict],
    hazard_zones,
) -> RouteCandidateOutput | None:
    """Fetch a route from Mapbox, score it against hazards and weather."""
    try:
        routes = await fetch_route(origin, destination, waypoints or None)
    except Exception as exc:
        logger.warning("Failed to fetch route for '%s': %s", label, exc)
        return None

    best, is_clear = _select_best_route(routes, hazard_polygons)
    geometry = best["geometry"]
    distance = best.get("distance", 0)
    duration = best.get("duration", 0) * CRISIS_TRAFFIC_FACTOR

    # Hazard assessment
    crossed = []
    for zone in hazard_zones:
        poly = shape(zone.polygon)
        line = shape(geometry)
        if line.intersects(poly):
            crossed.append(zone.hazard_id)

    if not crossed:
        hazard_exposure = "none"
    elif len(crossed) == 1:
        hazard_exposure = "low"
    elif len(crossed) <= 3:
        hazard_exposure = "medium"
    else:
        hazard_exposure = "high"

    # Weather assessment
    weather_points = await _sample_weather_along_route(geometry, num_points=3)
    weather_impact, weather_risks = _assess_weather_risk(weather_points)

    # Feasibility score: start at 100, deduct for hazards and weather
    score = 100.0
    score -= len(crossed) * 20  # -20 per hazard crossed
    weather_penalty = {"none": 0, "low": 5, "medium": 15, "high": 30}
    score -= weather_penalty.get(weather_impact, 0)
    # Slight penalty for longer routes (normalized to ~10 min baseline)
    score -= min(20, duration / 600 * 5)
    score = max(0, min(100, score))

    return RouteCandidateOutput(
        label=label,
        geometry=geometry,
        distance_meters=distance,
        duration_seconds=duration,
        feasibility_score=round(score, 1),
        hazard_exposure=hazard_exposure,
        weather_impact=weather_impact,
        hazards_crossed=crossed,
        weather_risks=weather_risks,
        reasoning="",  # filled by LLM or fallback
    )


# ── Agent class ──────────────────────────────────────────────────────

class RoutingAnalystAgent(BaseAgent[RoutingAnalystOutput]):
    agent_name = "routing_analyst"
    system_prompt = SYSTEM_PROMPT
    max_tokens = 800

    def build_user_prompt(self, context: dict) -> str:
        parts: list[str] = []
        parts.append(
            f"Origin: ({context['origin_lat']:.4f}, {context['origin_lng']:.4f}) → "
            f"Destination: ({context['dest_lat']:.4f}, {context['dest_lng']:.4f})"
        )

        candidates: list[RouteCandidateOutput] = context.get("candidates", [])
        parts.append(f"\n{len(candidates)} route candidate(s):\n")
        for c in candidates:
            parts.append(
                f"- **{c.label}**: {c.distance_meters:.0f}m, {c.duration_seconds:.0f}s, "
                f"hazard_exposure={c.hazard_exposure}, weather_impact={c.weather_impact}, "
                f"hazards_crossed={c.hazards_crossed}, weather_risks={c.weather_risks}, "
                f"score={c.feasibility_score}"
            )

        alerts = context.get("alerts", [])
        if alerts:
            parts.append(f"\nActive alerts ({len(alerts)}):")
            for a in alerts[:8]:
                title = getattr(a, "title", None) or getattr(a, "headline", str(a))
                parts.append(f"  - {title}")

        return "\n".join(parts)

    def parse_response(self, raw_text: str) -> RoutingAnalystOutput | None:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
            # Merge LLM assessments back into candidates
            candidates: list[RouteCandidateOutput] = self._context_candidates
            llm_assessments = {
                a["label"]: a for a in data.get("candidate_assessments", [])
            }
            for c in candidates:
                if c.label in llm_assessments:
                    a = llm_assessments[c.label]
                    c.feasibility_score = a.get("feasibility_score", c.feasibility_score)
                    c.hazard_exposure = a.get("hazard_exposure", c.hazard_exposure)
                    c.weather_impact = a.get("weather_impact", c.weather_impact)
                    c.reasoning = a.get("reasoning", "")

            return RoutingAnalystOutput(
                summary=data.get("summary", ""),
                recommended_route=data.get("recommended_route", candidates[0].label if candidates else ""),
                candidates=candidates,
                overall_assessment=data.get("overall_assessment", ""),
                evacuation_urgency=data.get("evacuation_urgency", "low"),
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    def fallback(self, context: dict) -> RoutingAnalystOutput:
        candidates: list[RouteCandidateOutput] = context.get("candidates", [])

        # Add reasoning to each candidate
        for c in candidates:
            parts = []
            if c.hazards_crossed:
                parts.append(f"Crosses {len(c.hazards_crossed)} hazard zone(s)")
            else:
                parts.append("Avoids all known hazards")
            if c.weather_risks:
                parts.append(f"Weather concerns: {', '.join(c.weather_risks)}")
            else:
                parts.append("No significant weather impact")
            c.reasoning = ". ".join(parts) + "."

        # Sort by feasibility score
        ranked = sorted(candidates, key=lambda c: c.feasibility_score, reverse=True)
        best = ranked[0] if ranked else None

        # Determine urgency
        any_high_hazard = any(c.hazard_exposure == "high" for c in candidates)
        all_crossed = all(len(c.hazards_crossed) > 0 for c in candidates) if candidates else False

        if all_crossed and any_high_hazard:
            urgency = "critical"
        elif any_high_hazard:
            urgency = "high"
        elif any(c.hazard_exposure == "medium" for c in candidates):
            urgency = "medium"
        else:
            urgency = "low"

        clear_count = sum(1 for c in candidates if not c.hazards_crossed)
        summary = (
            f"Evaluated {len(candidates)} route(s). "
            f"{clear_count} avoid all hazards. "
            f"{'Recommend: ' + best.label if best else 'No routes available'}."
        )

        return RoutingAnalystOutput(
            summary=summary,
            recommended_route=best.label if best else "",
            candidates=ranked,
            overall_assessment=(
                f"{'All routes cross hazard zones — proceed with extreme caution.' if all_crossed else ''} "
                f"Best option scores {best.feasibility_score:.0f}/100."
            ).strip() if best else "No feasible routes found.",
            evacuation_urgency=urgency,
        )

    async def run(self, context: dict) -> RoutingAnalystOutput:
        # Stash candidates so parse_response can merge LLM assessments
        self._context_candidates = context.get("candidates", [])
        return await super().run(context)


# ── Service function ─────────────────────────────────────────────────

async def generate_route_matrix(
    request: RouteMatrixRequest,
) -> AgentBriefingResponse:
    """Compute multiple route candidates, score them, and produce an assessment."""
    origin = Coordinate(lat=request.origin_lat, lng=request.origin_lng)
    destination = Coordinate(lat=request.destination_lat, lng=request.destination_lng)

    # Gather hazard and alert data
    hazard_zones = hazard_store.get_active_hazards()
    hazard_polygons = [z.polygon for z in hazard_zones]

    # Generate alternative waypoint sets
    alt_sets = _generate_alternative_waypoints(origin, destination, count=request.max_alternatives)

    # Also add the hazard-avoidance route if there are active hazards
    # (this uses the existing compute_route logic via waypoints)
    if hazard_zones:
        from app.services.mapbox_routing import _compute_waypoints_from_route
        # Get a baseline geometry first to compute avoidance waypoints
        try:
            direct_routes = await fetch_route(origin, destination)
            baseline_geom = direct_routes[0]["geometry"]
            avoidance_wps = _compute_waypoints_from_route(baseline_geom, hazard_polygons)
            if avoidance_wps:
                alt_sets.append(("Hazard-avoidance route", avoidance_wps))
        except Exception:
            logger.warning("Could not compute hazard-avoidance waypoints")

    # Build candidates in parallel
    tasks = [
        _build_candidate(label, origin, destination, wps, hazard_polygons, hazard_zones)
        for label, wps in alt_sets
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    candidates: list[RouteCandidateOutput] = []
    for r in results:
        if isinstance(r, RouteCandidateOutput):
            candidates.append(r)
        elif isinstance(r, Exception):
            logger.warning("Candidate build failed: %s", r)

    if not candidates:
        return AgentBriefingResponse(
            agent_type="routing_analyst",
            status="error",
            briefing="Failed to compute any route candidates.",
            structured_data={},
            data_sources=[],
            generated_at=datetime.utcnow(),
        )

    # Fetch alerts for LLM context
    try:
        alerts = await alerts_service.fetch_all_signals()
    except Exception:
        alerts = []

    context = {
        "origin_lat": request.origin_lat,
        "origin_lng": request.origin_lng,
        "dest_lat": request.destination_lat,
        "dest_lng": request.destination_lng,
        "candidates": candidates,
        "alerts": alerts,
    }

    agent = RoutingAnalystAgent()
    output = await agent.run(context)

    from app.core.config import settings
    import app.providers.watsonx_client as _mod

    status = "fallback" if (not settings.watsonx_api_key or _mod._watsonx_disabled) else "ok"

    return AgentBriefingResponse(
        agent_type="routing_analyst",
        status=status,
        briefing=output.summary,
        structured_data=output.model_dump(),
        data_sources=["mapbox", "open-meteo", "noaa-nws", "usgs", "nasa-firms", "gdacs"],
        generated_at=datetime.utcnow(),
    )
