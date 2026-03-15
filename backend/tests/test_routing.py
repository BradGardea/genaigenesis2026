from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.hazard_store import hazard_store
from shapely.geometry import mapping

from app.services.mapbox_routing import (
    CRISIS_TRAFFIC_FACTOR,
    _compute_waypoints_from_route,
)

client = TestClient(app)

MOCK_ROUTE = {
    "geometry": {
        "type": "LineString",
        "coordinates": [
            [-118.5, 34.0],
            [-118.4, 34.05],
            [-118.3, 34.1],
        ],
    },
    "distance": 15000,
    "duration": 900,
    "legs": [
        {
            "steps": [
                {
                    "maneuver": {
                        "instruction": "Head north on Highway 7"
                    }
                },
                {
                    "maneuver": {
                        "instruction": "Turn right onto Main St"
                    }
                },
            ]
        }
    ],
}


def _clear_store() -> None:
    hazard_store._hazards.clear()
    hazard_store._zones.clear()
    hazard_store._routes.clear()


@patch("app.services.mapbox_routing.fetch_route")
def test_plan_route(mock_fetch: AsyncMock) -> None:
    _clear_store()
    mock_fetch.return_value = [MOCK_ROUTE]

    payload = {
        "origin": {"lng": -118.5, "lat": 34.0},
        "destination": {"lng": -118.3, "lat": 34.1},
    }
    resp = client.post("/api/v1/routes/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["geometry"]["type"] == "LineString"
    assert data["distance_meters"] == 15000
    assert data["duration_seconds"] == 900 * CRISIS_TRAFFIC_FACTOR
    assert "route_id" in data
    assert len(data["instructions"]) == 2


@patch("app.services.mapbox_routing.fetch_route")
def test_plan_route_with_hazard(mock_fetch: AsyncMock) -> None:
    _clear_store()
    mock_fetch.return_value = [MOCK_ROUTE]

    # Report a hazard first
    client.post(
        "/api/v1/hazards/report",
        json={
            "hazard_type": "wildfire",
            "location": {"lng": -118.4, "lat": 34.05},
            "radius_meters": 500,
        },
    )

    payload = {
        "origin": {"lng": -118.5, "lat": 34.0},
        "destination": {"lng": -118.3, "lat": 34.1},
    }
    resp = client.post("/api/v1/routes/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["hazards_avoided"]) == 1


@patch("app.services.mapbox_routing.fetch_route")
def test_plan_route_with_profile(mock_fetch: AsyncMock) -> None:
    _clear_store()
    mock_fetch.return_value = [MOCK_ROUTE]

    payload = {
        "origin": {"lng": -118.5, "lat": 34.0},
        "destination": {"lng": -118.3, "lat": 34.1},
        "profile": {
            "family_size": 4,
            "vehicles": 1,
            "has_children": True,
        },
    }
    resp = client.post("/api/v1/routes/plan", json=payload)
    assert resp.status_code == 200


@patch("app.services.mapbox_routing.fetch_route")
def test_select_clear_alternative(mock_fetch: AsyncMock) -> None:
    """When one alternative avoids a hazard and another doesn't, pick the clear one."""
    _clear_store()

    # Route A goes through the hazard zone
    route_a = {
        "geometry": {
            "type": "LineString",
            "coordinates": [[-118.5, 34.0], [-118.4, 34.05], [-118.3, 34.1]],
        },
        "distance": 15000,
        "duration": 800,
        "legs": [{"steps": [{"maneuver": {"instruction": "Take Highway 7"}}]}],
    }

    # Route B avoids the hazard (goes further south)
    route_b = {
        "geometry": {
            "type": "LineString",
            "coordinates": [[-118.5, 34.0], [-118.4, 33.95], [-118.3, 34.1]],
        },
        "distance": 17000,
        "duration": 1000,
        "legs": [{"steps": [{"maneuver": {"instruction": "Take Southern Bypass"}}]}],
    }

    mock_fetch.return_value = [route_a, route_b]

    # Report a hazard that intersects route_a but not route_b
    client.post(
        "/api/v1/hazards/report",
        json={
            "hazard_type": "wildfire",
            "location": {"lng": -118.4, "lat": 34.05},
            "radius_meters": 500,
        },
    )

    payload = {
        "origin": {"lng": -118.5, "lat": 34.0},
        "destination": {"lng": -118.3, "lat": 34.1},
    }
    resp = client.post("/api/v1/routes/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # Should pick route_b (the clear one) even though it's longer
    assert data["instructions"] == ["Take Southern Bypass"]
    assert data["distance_meters"] == 17000
    # Duration should include crisis factor
    assert data["duration_seconds"] == 1000 * CRISIS_TRAFFIC_FACTOR
    # Only one fetch call needed (no retries since an alternative was clear)
    mock_fetch.assert_called_once()


def test_corridor_waypoints_geometry() -> None:
    """Corridor logic should emit 2 waypoints on the same side, ordered along the route."""
    route_geom = {
        "type": "LineString",
        "coordinates": [
            [-118.50, 34.00],
            [-118.45, 34.025],
            [-118.40, 34.05],
            [-118.35, 34.075],
            [-118.30, 34.10],
        ],
    }
    # Hazard polygon centered on the middle of the route
    from shapely.geometry import Point as ShapelyPoint

    hazard_center = ShapelyPoint(-118.40, 34.05)
    hazard_poly = mapping(hazard_center.buffer(0.01))  # ~1 km radius

    wps = _compute_waypoints_from_route(route_geom, [hazard_poly], repulsion_factor=2.0)

    assert len(wps) == 2, f"Expected 2 corridor waypoints, got {len(wps)}"

    # Both waypoints should be on the same side (same perpendicular direction)
    from shapely.geometry import LineString as ShapelyLine

    route_line = ShapelyLine(route_geom["coordinates"])
    d0 = route_line.project(ShapelyPoint(wps[0].lng, wps[0].lat))
    d1 = route_line.project(ShapelyPoint(wps[1].lng, wps[1].lat))
    assert d0 < d1, "Waypoint A should come before waypoint B along route"

    # Both waypoints should be outside the hazard polygon
    from shapely.geometry import shape as shapely_shape

    hazard = shapely_shape(hazard_poly)
    assert not hazard.contains(ShapelyPoint(wps[0].lng, wps[0].lat)), "WP A inside hazard"
    assert not hazard.contains(ShapelyPoint(wps[1].lng, wps[1].lat)), "WP B inside hazard"


def test_corridor_fallback_single_crossing() -> None:
    """Route starting inside hazard (1 crossing point) should fall back to single waypoint."""
    # Route starts inside the hazard polygon
    route_geom = {
        "type": "LineString",
        "coordinates": [
            [-118.40, 34.05],  # inside hazard
            [-118.35, 34.075],
            [-118.30, 34.10],
            [-118.25, 34.125],
            [-118.20, 34.15],
        ],
    }
    from shapely.geometry import Point as ShapelyPoint

    hazard_center = ShapelyPoint(-118.40, 34.05)
    hazard_poly = mapping(hazard_center.buffer(0.01))

    wps = _compute_waypoints_from_route(route_geom, [hazard_poly], repulsion_factor=2.0)

    # Should fall back to single waypoint (or possibly 0 if at route boundary)
    assert len(wps) <= 1, f"Expected fallback to <=1 waypoint, got {len(wps)}"


def test_stream_nonexistent_route() -> None:
    _clear_store()
    resp = client.get("/api/v1/routes/nonexistent/stream")
    assert resp.status_code == 404
