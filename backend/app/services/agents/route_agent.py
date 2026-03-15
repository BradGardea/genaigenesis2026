"""Agent 3 — Routing.

Consumes a PersonRiskProfile and calls Mapbox to produce ranked routes
scored against the avoid polygons and unsafe zones.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from shapely.geometry import shape

from app.models.routing import Coordinate
from app.schemas.agent_models import (
    LatLng,
    MatrixScore,
    PersonRiskProfile,
    RankedRoute,
    RoutingOutput,
)
from app.services.mapbox_routing import (
    CRISIS_TRAFFIC_FACTOR,
    _compute_waypoints_from_route,
    _route_intersects_hazards,
    fetch_route,
)

logger = logging.getLogger(__name__)


def _extract_instructions(route: dict) -> list[str]:
    """Extract turn-by-turn instructions from a Mapbox route."""
    instructions: list[str] = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            maneuver = step.get("maneuver", {})
            text = maneuver.get("instruction", "")
            if text:
                instructions.append(text)
    return instructions


async def compute_routes(risk_profile: PersonRiskProfile, check_isochrone: bool = False) -> RoutingOutput:
    """Execute Agent 3: compute ranked routes using avoid polygons from the risk profile."""
    routing_id = f"route-run-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    # Determine origin/destination
    # Risk profile contains the user_id; we need the actual coordinates.
    # These are carried through from the orchestrator via suggested_destinations
    # or the original person context. The risk profile avoid_polygons drive routing.

    # We need origin/destination from the orchestrator context.
    # They're passed via the function signature in the orchestrate_agent.
    # For the standalone endpoint, they must be reconstructed from risk_profile context.
    # The orchestrate_agent passes them directly.

    return RoutingOutput(
        routing_id=routing_id,
        generated_at=now,
        user_id=risk_profile.user_id,
        origin=LatLng(lat=0, lng=0),
        destination_used=LatLng(lat=0, lng=0),
        ranked_routes=[],
        recommendation="Use the orchestrate endpoint for full routing.",
        zones_on_best_route=0,
        total_zones_in_area=len(risk_profile.relevant_zones),
    )


async def compute_routes_with_coords(
    risk_profile: PersonRiskProfile,
    origin: LatLng,
    destination: LatLng,
    check_isochrone: bool = False,
) -> RoutingOutput:
    """Compute ranked routes given explicit origin/destination and risk profile."""
    routing_id = f"route-run-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    origin_coord = Coordinate(lat=origin.lat, lng=origin.lng)
    dest_coord = Coordinate(lat=destination.lat, lng=destination.lng)
    avoid_polygons = risk_profile.avoid_polygons

    all_zone_ids = [z.zone_id for z in risk_profile.relevant_zones]
    ranked: list[RankedRoute] = []

    # ── Route 1: Safest (with full hazard avoidance) ──────────
    try:
        direct_routes = await fetch_route(origin_coord, dest_coord)
        baseline_geom = direct_routes[0]["geometry"]

        waypoints = _compute_waypoints_from_route(baseline_geom, avoid_polygons, repulsion_factor=2.0)
        if waypoints:
            safe_routes = await fetch_route(origin_coord, dest_coord, waypoints)
        else:
            safe_routes = direct_routes

        safe_route = safe_routes[0]
        safe_geom = safe_route["geometry"]
        safe_dist = safe_route.get("distance", 0)
        safe_dur = safe_route.get("duration", 0) * CRISIS_TRAFFIC_FACTOR
        safe_instructions = _extract_instructions(safe_route)

        # Determine zones crossed/avoided
        crossed_safe = []
        avoided_safe = []
        for zone in risk_profile.relevant_zones:
            if zone.polygon:
                try:
                    poly = shape(zone.polygon)
                    line = shape(safe_geom)
                    if line.intersects(poly):
                        crossed_safe.append(zone.zone_id)
                    else:
                        avoided_safe.append(zone.zone_id)
                except Exception:
                    pass

        risk_score_safe = min(1.0, len(crossed_safe) * 0.25)
        wp_latlng = [LatLng(lat=w.lat, lng=w.lng) for w in waypoints] if waypoints else []

        note_safe = "Clears all active hazard zones." if not crossed_safe else f"Crosses {len(crossed_safe)} zone(s)."
        if direct_routes[0].get("duration", 0) > 0:
            added_min = round((safe_dur - direct_routes[0]["duration"] * CRISIS_TRAFFIC_FACTOR) / 60, 0)
            if added_min > 0:
                note_safe += f" Adds {added_min:.0f} min vs fastest."

        ranked.append(RankedRoute(
            rank=1,
            route_id=f"route-{uuid.uuid4().hex[:8]}",
            label="Safest route",
            geometry=safe_geom,
            distance_meters=safe_dist,
            duration_seconds=safe_dur,
            eta_minutes=round(safe_dur / 60, 1),
            risk_score=risk_score_safe,
            zones_crossed=crossed_safe,
            zones_avoided=avoided_safe,
            avoidance_waypoints_used=wp_latlng,
            instructions=safe_instructions,
            note=note_safe,
        ))

        # ── Route 2: Faster — partial avoidance ──────────────────
        # Use only the most dangerous polygons (severity >= 65)
        critical_polygons = [
            z.polygon for z in risk_profile.relevant_zones
            if z.polygon and z.severity >= 65
        ]
        if critical_polygons and len(critical_polygons) < len(avoid_polygons):
            partial_wps = _compute_waypoints_from_route(baseline_geom, critical_polygons, repulsion_factor=1.5)
            if partial_wps:
                partial_routes = await fetch_route(origin_coord, dest_coord, partial_wps)
            else:
                partial_routes = direct_routes
            partial_route = partial_routes[0]
            partial_geom = partial_route["geometry"]
            partial_dist = partial_route.get("distance", 0)
            partial_dur = partial_route.get("duration", 0) * CRISIS_TRAFFIC_FACTOR

            crossed_partial = []
            avoided_partial = []
            for zone in risk_profile.relevant_zones:
                if zone.polygon:
                    try:
                        poly = shape(zone.polygon)
                        line = shape(partial_geom)
                        if line.intersects(poly):
                            crossed_partial.append(zone.zone_id)
                        else:
                            avoided_partial.append(zone.zone_id)
                    except Exception:
                        pass

            moderate_types = set()
            for zid in crossed_partial:
                for z in risk_profile.relevant_zones:
                    if z.zone_id == zid:
                        moderate_types.add(z.impact_type)

            label2 = f"Faster route — {len(crossed_partial)} moderate zone(s)" if crossed_partial else "Faster route"
            ranked.append(RankedRoute(
                rank=2,
                route_id=f"route-{uuid.uuid4().hex[:8]}",
                label=label2,
                geometry=partial_geom,
                distance_meters=partial_dist,
                duration_seconds=partial_dur,
                eta_minutes=round(partial_dur / 60, 1),
                risk_score=min(1.0, len(crossed_partial) * 0.2),
                zones_crossed=crossed_partial,
                zones_avoided=avoided_partial,
                avoidance_waypoints_used=[],
                instructions=_extract_instructions(partial_route),
                note=f"Passes through {len(crossed_partial)} moderate zone(s)." if crossed_partial else "Faster with minimal exposure.",
            ))

        # ── Route 3: Fastest — direct, no avoidance ──────────────
        direct_route = direct_routes[0]
        direct_geom = direct_route["geometry"]
        direct_dist = direct_route.get("distance", 0)
        direct_dur = direct_route.get("duration", 0) * CRISIS_TRAFFIC_FACTOR

        crossed_direct = []
        avoided_direct = []
        for zone in risk_profile.relevant_zones:
            if zone.polygon:
                try:
                    poly = shape(zone.polygon)
                    line = shape(direct_geom)
                    if line.intersects(poly):
                        crossed_direct.append(zone.zone_id)
                    else:
                        avoided_direct.append(zone.zone_id)
                except Exception:
                    pass

        direct_recommended = len(crossed_direct) == 0
        ranked.append(RankedRoute(
            rank=len(ranked) + 1,
            route_id=f"route-{uuid.uuid4().hex[:8]}",
            label="Fastest route" if direct_recommended else "Fastest route — not recommended",
            geometry=direct_geom,
            distance_meters=direct_dist,
            duration_seconds=direct_dur,
            eta_minutes=round(direct_dur / 60, 1),
            risk_score=min(1.0, len(crossed_direct) * 0.25),
            zones_crossed=crossed_direct,
            zones_avoided=avoided_direct,
            avoidance_waypoints_used=[],
            instructions=_extract_instructions(direct_route),
            note="Not recommended. Passes through active hazard zones." if crossed_direct else "Direct route is clear.",
        ))

    except Exception:
        logger.exception("Route computation failed")

    # ── Build recommendation ──────────────────────────────────
    best = ranked[0] if ranked else None
    zones_on_best = len(best.zones_crossed) if best else 0
    recommendation = ""
    if best:
        if zones_on_best == 0:
            recommendation = f"Take Route 1 ({best.label}). Avoids all active hazard zones."
        else:
            recommendation = f"Take Route 1 ({best.label}). Crosses {zones_on_best} zone(s) — proceed with caution."

    return RoutingOutput(
        routing_id=routing_id,
        generated_at=now,
        user_id=risk_profile.user_id,
        origin=origin,
        destination_used=destination,
        ranked_routes=ranked,
        matrix_scores=[],
        isochrone_30min=None,
        recommendation=recommendation,
        zones_on_best_route=zones_on_best,
        total_zones_in_area=len(risk_profile.relevant_zones),
    )
