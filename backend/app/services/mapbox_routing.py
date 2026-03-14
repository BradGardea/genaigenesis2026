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


def compute_avoidance_waypoints(
    origin: Coordinate,
    destination: Coordinate,
    hazard_polygons: list[dict],
    repulsion_factor: float = 1.5,
) -> list[Coordinate]:
    """Compute waypoints that push the route away from hazard zones.

    For each hazard whose centroid is near the direct path, place a waypoint
    on the opposite side of the path from the hazard centroid.
    """
    if not hazard_polygons:
        return []

    ox, oy = origin.lng, origin.lat
    dx, dy = destination.lng, destination.lat
    path_vec = (dx - ox, dy - oy)
    path_len = math.hypot(*path_vec)
    if path_len == 0:
        return []

    waypoints: list[Coordinate] = []
    for poly_geojson in hazard_polygons:
        poly = shape(poly_geojson)
        cx, cy = poly.centroid.x, poly.centroid.y

        # Project centroid onto the origin→destination line
        t = ((cx - ox) * path_vec[0] + (cy - oy) * path_vec[1]) / (path_len**2)
        if t < 0.05 or t > 0.95:
            continue  # hazard is near endpoints; waypoint won't help much

        # Perpendicular offset: push away from hazard centroid
        proj_x = ox + t * path_vec[0]
        proj_y = oy + t * path_vec[1]
        perp_x = cx - proj_x
        perp_y = cy - proj_y
        perp_len = math.hypot(perp_x, perp_y)
        if perp_len == 0:
            perp_x, perp_y = -path_vec[1], path_vec[0]
            perp_len = math.hypot(perp_x, perp_y)

        # Radius in degrees (rough)
        bounds = poly.bounds  # (minx, miny, maxx, maxy)
        radius_deg = max(bounds[2] - bounds[0], bounds[3] - bounds[1]) / 2

        offset = radius_deg * repulsion_factor
        wp_x = proj_x - (perp_x / perp_len) * offset
        wp_y = proj_y - (perp_y / perp_len) * offset

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
    """Compute a route avoiding hazard zones, with retry on intersection."""

    repulsion = 1.5
    for attempt in range(MAX_RETRIES + 1):
        waypoints = compute_avoidance_waypoints(
            origin, destination, hazard_polygons, repulsion_factor=repulsion
        )
        route = await fetch_route(origin, destination, waypoints)

        geometry = route["geometry"]
        if not hazard_polygons or not _route_intersects_hazards(geometry, hazard_polygons):
            route["_avoidance_waypoints"] = [
                {"lng": w.lng, "lat": w.lat} for w in waypoints
            ]
            return route

        logger.warning(
            "Route attempt %d intersects hazards, retrying with more repulsion",
            attempt + 1,
        )
        repulsion *= 2.0

    # Return last attempt even if it still intersects
    route["_avoidance_waypoints"] = [{"lng": w.lng, "lat": w.lat} for w in waypoints]
    return route
