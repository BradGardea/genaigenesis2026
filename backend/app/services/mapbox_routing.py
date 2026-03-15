from __future__ import annotations

import logging
import math

import httpx
from shapely.geometry import GeometryCollection, LineString, MultiPoint, Point, mapping, shape

from app.core.config import settings
from app.models.routing import Coordinate

logger = logging.getLogger(__name__)

MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/driving-traffic"
MAX_RETRIES = 2
MIN_OFFSET_DEG = 0.008  # ~900 m — reaches major arterials, skips residential dead-ends
CRISIS_TRAFFIC_FACTOR = 1.5  # multiplier for durations to reflect evacuation congestion
WAYPOINT_SNAP_RADIUS_M = 25  # max metres Mapbox may move an avoidance waypoint when snapping
ENTRY_EXIT_MARGIN_DEG = 0.002  # ~220 m buffer before entry / after exit of hazard
MAX_AVOIDANCE_WAYPOINTS = 20


def _extract_points(geom) -> list[Point]:
    """Extract Point objects from a Shapely intersection result."""
    if geom.is_empty:
        return []
    if isinstance(geom, Point):
        return [geom]
    if isinstance(geom, MultiPoint):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        pts = []
        for g in geom.geoms:
            if isinstance(g, Point):
                pts.append(g)
            elif isinstance(g, MultiPoint):
                pts.extend(g.geoms)
        return pts
    # LineString (tangent case) — use endpoints
    if isinstance(geom, LineString):
        coords = list(geom.coords)
        if len(coords) >= 2:
            return [Point(coords[0]), Point(coords[-1])]
    return []


def _add_single_waypoint(
    route_line: LineString,
    poly,
    repulsion_factor: float,
) -> Coordinate | None:
    """Fallback: place a single perpendicular waypoint (original V-detour logic)."""
    centroid = poly.centroid
    d = route_line.project(centroid)

    if d < route_line.length * 0.05 or d > route_line.length * 0.95:
        return None

    nearest = route_line.interpolate(d)

    eps = max(route_line.length * 0.01, 0.0001)
    p_before = route_line.interpolate(max(0, d - eps))
    p_after = route_line.interpolate(min(route_line.length, d + eps))
    tx = p_after.x - p_before.x
    ty = p_after.y - p_before.y
    tlen = math.hypot(tx, ty)
    if tlen == 0:
        return None

    perp_x = -ty / tlen
    perp_y = tx / tlen

    dx = centroid.x - nearest.x
    dy = centroid.y - nearest.y
    side = dx * perp_x + dy * perp_y
    direction = -1.0 if side > 0 else 1.0

    bounds = poly.bounds
    radius_deg = max(bounds[2] - bounds[0], bounds[3] - bounds[1]) / 2
    offset = max(radius_deg * repulsion_factor, MIN_OFFSET_DEG)

    wp_x = nearest.x + direction * perp_x * offset
    wp_y = nearest.y + direction * perp_y * offset
    return Coordinate(lng=round(wp_x, 6), lat=round(wp_y, 6))


def _compute_waypoints_from_route(
    route_geometry: dict,
    hazard_polygons: list[dict],
    repulsion_factor: float = 2.0,
) -> list[Coordinate]:
    """Place entry/exit corridor waypoints around each hazard.

    Instead of a single perpendicular waypoint (V-detour), emit two waypoints —
    one before the route enters the hazard and one after it exits — both offset
    to the same side. This creates a rectangular corridor along a parallel street.
    Falls back to a single waypoint when fewer than 2 crossing points exist.
    """
    if not hazard_polygons:
        return []

    route_line = LineString(route_geometry["coordinates"])
    # Collect (projected_distance, Coordinate) tuples for final sorting
    wp_with_dist: list[tuple[float, Coordinate]] = []

    for poly_geojson in hazard_polygons:
        poly = shape(poly_geojson)
        if not route_line.intersects(poly):
            continue

        # Find where the route crosses the hazard boundary
        crossing = route_line.intersection(poly.boundary)
        points = _extract_points(crossing)

        if len(points) < 2:
            # Degenerate case: route starts/ends inside hazard or tangent
            wp = _add_single_waypoint(route_line, poly, repulsion_factor)
            if wp is not None:
                d = route_line.project(Point(wp.lng, wp.lat))
                wp_with_dist.append((d, wp))
            continue

        # Project crossing points onto route and sort by distance
        projected = sorted(
            [(route_line.project(p), p) for p in points], key=lambda t: t[0]
        )
        entry_d = projected[0][0]
        exit_d = projected[-1][0]

        # Compute tangent at midpoint between entry and exit
        mid_d = (entry_d + exit_d) / 2
        eps = max(route_line.length * 0.01, 0.0001)
        p_before = route_line.interpolate(max(0, mid_d - eps))
        p_after = route_line.interpolate(min(route_line.length, mid_d + eps))
        tx = p_after.x - p_before.x
        ty = p_after.y - p_before.y
        tlen = math.hypot(tx, ty)
        if tlen == 0:
            continue

        # Perpendicular direction
        perp_x = -ty / tlen
        perp_y = tx / tlen

        # Push away from hazard centroid
        centroid = poly.centroid
        mid_pt = route_line.interpolate(mid_d)
        dx = centroid.x - mid_pt.x
        dy = centroid.y - mid_pt.y
        side = dx * perp_x + dy * perp_y
        direction = -1.0 if side > 0 else 1.0

        bounds = poly.bounds
        radius_deg = max(bounds[2] - bounds[0], bounds[3] - bounds[1]) / 2
        offset = max(radius_deg * repulsion_factor, MIN_OFFSET_DEG)

        # Waypoint A: before entry
        d_a = max(0, entry_d - ENTRY_EXIT_MARGIN_DEG)
        if d_a >= route_line.length * 0.05:
            pt_a = route_line.interpolate(d_a)
            wp_a = Coordinate(
                lng=round(pt_a.x + direction * perp_x * offset, 6),
                lat=round(pt_a.y + direction * perp_y * offset, 6),
            )
            wp_with_dist.append((d_a, wp_a))

        # Waypoint B: after exit
        d_b = min(route_line.length, exit_d + ENTRY_EXIT_MARGIN_DEG)
        if d_b <= route_line.length * 0.95:
            pt_b = route_line.interpolate(d_b)
            wp_b = Coordinate(
                lng=round(pt_b.x + direction * perp_x * offset, 6),
                lat=round(pt_b.y + direction * perp_y * offset, 6),
            )
            wp_with_dist.append((d_b, wp_b))

    # Sort all waypoints by distance along route for correct ordering
    wp_with_dist.sort(key=lambda t: t[0])
    return [wp for _, wp in wp_with_dist]


def _route_intersects_hazards(
    geometry: dict, hazard_polygons: list[dict]
) -> bool:
    line = shape(geometry)
    for poly_geojson in hazard_polygons:
        poly = shape(poly_geojson)
        if line.intersects(poly):
            return True
    return False


def _select_best_route(
    routes: list[dict], hazard_polygons: list[dict]
) -> tuple[dict, bool]:
    """Pick the best route from a list of candidates.

    Returns the shortest-duration route that avoids all hazards. If none are
    clear, returns the shortest-duration overall. The boolean indicates whether
    the selected route is hazard-free.
    """
    clear = [r for r in routes if not _route_intersects_hazards(r["geometry"], hazard_polygons)]
    if clear:
        best = min(clear, key=lambda r: r.get("duration", float("inf")))
        return best, True
    best = min(routes, key=lambda r: r.get("duration", float("inf")))
    return best, False


def _apply_crisis_factor(route: dict, factor: float) -> None:
    """Scale duration and per-segment annotation durations in place."""
    if "duration" in route:
        route["duration"] = route["duration"] * factor
    for leg in route.get("legs", []):
        ann = leg.get("annotation", {})
        if "duration" in ann:
            ann["duration"] = [d * factor for d in ann["duration"]]


async def fetch_route(
    origin: Coordinate,
    destination: Coordinate,
    waypoints: list[Coordinate] | None = None,
) -> list[dict]:
    """Call Mapbox Directions API and return all route candidates."""
    coords_parts = [f"{origin.lng},{origin.lat}"]
    for wp in waypoints or []:
        coords_parts.append(f"{wp.lng},{wp.lat}")
    coords_parts.append(f"{destination.lng},{destination.lat}")
    coords_str = ";".join(coords_parts)

    url = f"{MAPBOX_DIRECTIONS_URL}/{coords_str}"
    params: dict = {
        "access_token": settings.mapbox_access_token,
        "geometries": "geojson",
        "overview": "full",
        "steps": "true",
        "annotations": "duration",
        "exclude": "unpaved",
        "alternatives": "true",
        "continue_straight": "true",
    }

    # Constrain waypoint snapping radius so Mapbox doesn't slide avoidance
    # waypoints onto dead-end streets or service roads far from the intended
    # perpendicular offset.  Origin and destination use "unlimited".
    if waypoints:
        radiuses = ["unlimited"] + [str(WAYPOINT_SNAP_RADIUS_M)] * len(waypoints) + ["unlimited"]
        params["radiuses"] = ";".join(radiuses)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        # If snapping radius is too tight Mapbox returns 422; retry without it
        if resp.status_code == 422 and "radiuses" in params:
            logger.warning("Waypoint snapping radius too tight, retrying without radius constraint")
            params.pop("radiuses")
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    routes = data.get("routes", [])
    if not routes:
        raise ValueError("Mapbox returned no routes")
    return routes


async def compute_route(
    origin: Coordinate,
    destination: Coordinate,
    hazard_polygons: list[dict],
    crisis_traffic_factor: float = CRISIS_TRAFFIC_FACTOR,
) -> dict:
    """Compute a route avoiding hazard zones, using alternatives-first strategy.

    1. Fetch routes with alternatives (up to 3 candidates per API call).
    2. If any alternative already avoids all hazards, return it immediately.
    3. Otherwise, compute avoidance waypoints from the best route geometry and
       retry with increasing repulsion (up to MAX_RETRIES).
    4. Apply crisis traffic factor to the final route's durations.
    """
    routes = await fetch_route(origin, destination)
    route, is_clear = _select_best_route(routes, hazard_polygons)
    geometry = route["geometry"]

    if not hazard_polygons or is_clear:
        route["_avoidance_waypoints"] = []
        _apply_crisis_factor(route, crisis_traffic_factor)
        return route

    repulsion = 2.0
    waypoints: list[Coordinate] = []

    for attempt in range(MAX_RETRIES + 1):
        waypoints = _compute_waypoints_from_route(
            geometry, hazard_polygons, repulsion_factor=repulsion
        )
        if len(waypoints) > MAX_AVOIDANCE_WAYPOINTS:
            logger.warning(
                "Generated %d avoidance waypoints; truncating to %d",
                len(waypoints),
                MAX_AVOIDANCE_WAYPOINTS,
            )
            waypoints = waypoints[:MAX_AVOIDANCE_WAYPOINTS]

        try:
            routes = await fetch_route(origin, destination, waypoints)
        except ValueError:
            logger.warning(
                "Avoidance attempt %d returned no routes; keeping best known route",
                attempt + 1,
            )
            break
        route, is_clear = _select_best_route(routes, hazard_polygons)
        geometry = route["geometry"]

        if is_clear:
            route["_avoidance_waypoints"] = [
                {"lng": w.lng, "lat": w.lat} for w in waypoints
            ]
            _apply_crisis_factor(route, crisis_traffic_factor)
            return route

        logger.warning(
            "Route attempt %d still intersects hazards, retrying with more repulsion",
            attempt + 1,
        )
        repulsion *= 2.0

    route["_avoidance_waypoints"] = [{"lng": w.lng, "lat": w.lat} for w in waypoints]
    _apply_crisis_factor(route, crisis_traffic_factor)
    return route
