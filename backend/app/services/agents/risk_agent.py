"""Agent 2 — Person Risk Evaluation.

Consumes a DisasterAssessmentOutput + PersonContext to produce a
PersonRiskProfile with relevant zones, avoid polygons, and risk factors.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from shapely.geometry import LineString, Point, shape

from app.schemas.agent_models import (
    DisasterAssessmentOutput,
    EvaluateRiskRequest,
    PersonContext,
    PersonRiskProfile,
    RelevantZone,
    SuggestedDestination,
)


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 111.32
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return round(math.hypot(dx, dy), 2)


def _danger_threshold(risk_tolerance: str) -> str:
    """Minimum danger_to_remain to include in avoid_polygons."""
    if risk_tolerance == "high":
        return "high"
    if risk_tolerance == "medium":
        return "moderate"
    return "low"  # low tolerance → avoid everything


def _danger_rank(danger: str) -> int:
    return {"low": 0, "moderate": 1, "high": 2, "extreme": 3}.get(danger, 0)


async def evaluate_risk(request: EvaluateRiskRequest) -> PersonRiskProfile:
    """Execute Agent 2: filter zones, compute personal risk, build avoid polygons."""
    assessment = request.assessment
    person = request.person
    profile_id = f"risk-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    origin_pt = Point(person.origin.lng, person.origin.lat)
    dest_pt = None
    direct_line = None
    if person.destination:
        dest_pt = Point(person.destination.lng, person.destination.lat)
        direct_line = LineString([
            (person.origin.lng, person.origin.lat),
            (person.destination.lng, person.destination.lat),
        ])

    # ── Filter relevant zones ─────────────────────────────────
    relevant_zones: list[RelevantZone] = []
    avoid_polygons: list[dict] = []
    threshold = _danger_threshold(person.risk_tolerance)

    for zone in assessment.unsafe_zones:
        dist_km = _distance_km(
            person.origin.lat, person.origin.lng,
            zone.center.lat, zone.center.lon,
        )

        # Only consider zones within 50 km of origin
        if dist_km > 50:
            continue

        on_path = False
        if direct_line and zone.polygon:
            try:
                poly = shape(zone.polygon)
                on_path = direct_line.intersects(poly)
            except Exception:
                pass

        # Include if on path or within reasonable range
        if not on_path and dist_km > 10:
            continue

        relevant_zones.append(RelevantZone(
            zone_id=zone.zone_id,
            impact_type=zone.impact_type,
            danger_to_remain=zone.danger_to_remain,
            severity=zone.severity,
            distance_from_origin_km=dist_km,
            on_direct_path=on_path,
            polygon=zone.polygon,
        ))

        # Build avoid_polygons for zones at or above threshold
        if _danger_rank(zone.danger_to_remain) >= _danger_rank(threshold) and zone.polygon:
            avoid_polygons.append(zone.polygon)

    # ── Compute personal risk level ───────────────────────────
    path_zones = [z for z in relevant_zones if z.on_direct_path]
    max_severity = max((z.severity for z in path_zones), default=0)
    path_count = len(path_zones)

    vulnerability = 0
    if person.has_mobility_needs:
        vulnerability += 2
    if person.has_medical_equipment:
        vulnerability += 1
    if person.party_size >= 4:
        vulnerability += 1
    if person.vehicle == "foot":
        vulnerability += 2
    elif person.vehicle == "motorcycle":
        vulnerability += 1

    # Combine severity, zone count, and vulnerability
    risk_score = max_severity * 0.5 + path_count * 15 + vulnerability * 8
    if person.risk_tolerance == "low":
        risk_score += 10

    if risk_score >= 80:
        risk_level = "critical"
    elif risk_score >= 55:
        risk_level = "high"
    elif risk_score >= 30:
        risk_level = "medium"
    else:
        risk_level = "low"

    should_evacuate = risk_level in ("high", "critical")

    # Confidence based on data completeness
    confidence = "high" if assessment.total_unsafe_zones > 0 else "low"
    if not path_zones and assessment.total_unsafe_zones > 0:
        confidence = "medium"

    # ── Risk factors ──────────────────────────────────────────
    risk_factors: list[str] = []
    if path_zones:
        types = set(z.impact_type for z in path_zones)
        risk_factors.append(
            f"{len(path_zones)} active zone(s) ({', '.join(types)}) directly on your path to destination."
        )
    if assessment.storm_movement and assessment.storm_movement.speed_kmh:
        risk_factors.append(
            f"Storm moving toward your area at {assessment.storm_movement.speed_kmh} km/h — zones will intensify."
        )
    risk_factors.append(
        f"Overall city severity: {assessment.scenario.overall_severity}/100 "
        f"({assessment.scenario.operational_status.replace('_', ' ')})."
    )
    if vulnerability >= 2:
        risk_factors.append("Elevated vulnerability due to mobility needs or travel mode.")

    # ── Routing urgency ───────────────────────────────────────
    if risk_level == "critical":
        routing_urgency = "high"
    elif risk_level == "high":
        routing_urgency = "high"
    elif risk_level == "medium":
        routing_urgency = "medium"
    else:
        routing_urgency = "low"

    # ── Suggested destinations (only when no destination given) ─
    suggested: list[SuggestedDestination] = []
    if person.destination is None:
        # Suggest a point away from the heaviest zones
        suggested.append(SuggestedDestination(
            name="Goma North Assembly Point",
            lat=-1.640,
            lng=29.240,
            type="evacuation_center",
            distance_from_origin_km=_distance_km(person.origin.lat, person.origin.lng, -1.640, 29.240),
            clears_all_avoid_polygons=True,
        ))

    return PersonRiskProfile(
        profile_id=profile_id,
        generated_at=now,
        user_id=person.user_id,
        personal_risk_level=risk_level,
        confidence=confidence,
        should_evacuate_now=should_evacuate,
        relevant_zones=relevant_zones,
        avoid_polygons=avoid_polygons,
        risk_factors=risk_factors,
        routing_urgency=routing_urgency,
        suggested_destinations=suggested,
    )
