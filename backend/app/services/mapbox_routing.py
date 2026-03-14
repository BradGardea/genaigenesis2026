from __future__ import annotations

import logging
import math

import httpx
from shapely.geometry import LineString, mapping, shape

from app.core.config import settings
from app.models.routing import Coordinate

logger = logging.getLogger(__name__)

MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/driving"
MAX_RETRIES = 2
MIN_OFFSET_DEG = 0.003  # ~330 m — enough to reach a parallel street in a city grid


def _compute_waypoints_from_route(
    route_geometry: dict,
    hazard_polygons: list[dict],
    repulsion_factor: float = 2.0,
) -> list[Coordinate]:
    """Place avoidance waypoints perpendicular to the *actual road* at each hazard.

    Using the route geometry (not the OD straight line) gives a perpendicular
    direction that aligns with the local road orientation, so the waypoint
    naturally falls on a parallel street rather than causing Mapbox to create
    a circular detour.
    """
    if not hazard_polygons:
        return []

    route_line = LineString(route_geometry["coordinates"])
    waypoints: list[Coordinate] = []

    for poly_geojson in hazard_polygons:
        poly = shape(poly_geojson)
        if not route_line.intersects(poly):
            continue

        centroid = poly.centroid
        d = route_line.project(centroid)

        # Skip hazards at the very start/end of the route
        if d < route_line.length * 0.05 or d > route_line.length * 0.95:
            continue

        nearest = route_line.interpolate(d)

        # Route tangent at the hazard point
        eps = max(route_line.length * 0.01, 0.0001)
        p_before = route_line.interpolate(max(0, d - eps))
        p_after = route_line.interpolate(min(route_line.length, d + eps))
        tx = p_after.x - p_before.x
        ty = p_after.y - p_before.y
        tlen = math.hypot(tx, ty)
        if tlen == 0:
            continue

        # Perpendicular to route direction (rotated 90°)
        perp_x = -ty / tlen
        perp_y = tx / tlen

        # Determine which side of the route the hazard centroid is on
        dx = centroid.x - nearest.x
        dy = centroid.y - nearest.y
        side = dx * perp_x + dy * perp_y
        direction = -1.0 if side > 0 else 1.0

        bounds = poly.bounds
        radius_deg = max(bounds[2] - bounds[0], bounds[3] - bounds[1]) / 2
        offset = max(radius_deg * repulsion_factor, MIN_OFFSET_DEG)

        wp_x = nearest.x + direction * perp_x * offset
        wp_y = nearest.y + direction * perp_y * offset
        waypoints.append(Coordinate(lng=round(wp_x, 6), lat=round(wp_y, 6)))

    return waypoints


def _route_intersects_hazards(
    geometry: dict, hazard_polygons: list[dict]
) -> bool:
    line = shape(geometry)
    for poly_geojson in hazard_polygons:
        poly = shape(poly_geojson)
        if line.intersects(poly):
            return True
    return False


async def fetch_route(
    origin: Coordinate,
    destination: Coordinate,
    waypoints: list[Coordinate] | None = None,
) -> dict:
    """Call Mapbox Directions API and return the first route."""
    coords_parts = [f"{origin.lng},{origin.lat}"]
    for wp in waypoints or []:
        coords_parts.append(f"{wp.lng},{wp.lat}")
    coords_parts.append(f"{destination.lng},{destination.lat}")
    coords_str = ";".join(coords_parts)

    url = f"{MAPBOX_DIRECTIONS_URL}/{coords_str}"
    params = {
        "access_token": settings.mapbox_access_token,
        "geometries": "geojson",
        "overview": "full",
        "steps": "true",
        "annotations": "duration",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    routes = data.get("routes", [])
    if not routes:
        raise ValueError("Mapbox returned no routes")
    return routes[0]


async def compute_route(
    origin: Coordinate,
    destination: Coordinate,
    hazard_polygons: list[dict],
) -> dict:
    """Compute a route avoiding hazard zones, with retry on intersection.

    1. Fetch the natural route (no waypoints).
    2. If it intersects any hazard, compute avoidance waypoints *from the
       route geometry* so they're perpendicular to the actual road.
    3. Retry with increasing repulsion until the route is clear (or max retries).
    """
    route = await fetch_route(origin, destination)
    geometry = route["geometry"]

    if not hazard_polygons or not _route_intersects_hazards(geometry, hazard_polygons):
        route["_avoidance_waypoints"] = []
        return route

    repulsion = 2.0
    waypoints: list[Coordinate] = []

    for attempt in range(MAX_RETRIES + 1):
        waypoints = _compute_waypoints_from_route(
            geometry, hazard_polygons, repulsion_factor=repulsion
        )
        route = await fetch_route(origin, destination, waypoints)
        geometry = route["geometry"]

        if not _route_intersects_hazards(geometry, hazard_polygons):
            route["_avoidance_waypoints"] = [
                {"lng": w.lng, "lat": w.lat} for w in waypoints
            ]
            return route

        logger.warning(
            "Route attempt %d still intersects hazards, retrying with more repulsion",
            attempt + 1,
        )
        repulsion *= 2.0

    route["_avoidance_waypoints"] = [{"lng": w.lng, "lat": w.lat} for w in waypoints]
    return route
