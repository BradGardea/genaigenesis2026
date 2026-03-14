from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.hazard_store import hazard_store

client = TestClient(app)

MOCK_MAPBOX_RESPONSE = {
    "routes": [
        {
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
    ]
}


def _clear_store() -> None:
    hazard_store._hazards.clear()
    hazard_store._zones.clear()
    hazard_store._routes.clear()


@patch("app.services.mapbox_routing.fetch_route")
def test_plan_route(mock_fetch: AsyncMock) -> None:
    _clear_store()
    mock_fetch.return_value = MOCK_MAPBOX_RESPONSE["routes"][0]

    payload = {
        "origin": {"lng": -118.5, "lat": 34.0},
        "destination": {"lng": -118.3, "lat": 34.1},
    }
    resp = client.post("/api/v1/routes/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["geometry"]["type"] == "LineString"
    assert data["distance_meters"] == 15000
    assert data["duration_seconds"] == 900
    assert "route_id" in data
    assert len(data["instructions"]) == 2


@patch("app.services.mapbox_routing.fetch_route")
def test_plan_route_with_hazard(mock_fetch: AsyncMock) -> None:
    _clear_store()
    mock_fetch.return_value = MOCK_MAPBOX_RESPONSE["routes"][0]

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
    mock_fetch.return_value = MOCK_MAPBOX_RESPONSE["routes"][0]

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


def test_stream_nonexistent_route() -> None:
    _clear_store()
    resp = client.get("/api/v1/routes/nonexistent/stream")
    assert resp.status_code == 404
