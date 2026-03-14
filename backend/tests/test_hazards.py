from fastapi.testclient import TestClient

from app.main import app
from app.services.hazard_store import hazard_store

client = TestClient(app)


def _clear_store() -> None:
    hazard_store._hazards.clear()
    hazard_store._zones.clear()
    hazard_store._routes.clear()


def test_report_hazard() -> None:
    _clear_store()
    payload = {
        "hazard_type": "wildfire",
        "location": {"lng": -118.5, "lat": 34.0},
        "radius_meters": 1000,
        "description": "Brush fire near trailhead",
    }
    resp = client.post("/api/v1/hazards/report", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["hazard_type"] == "wildfire"
    assert "polygon" in data
    assert data["polygon"]["type"] == "Polygon"
    assert len(data["polygon"]["coordinates"]) > 0


def test_get_active_hazards() -> None:
    _clear_store()
    # Report two hazards
    for i in range(2):
        client.post(
            "/api/v1/hazards/report",
            json={
                "hazard_type": "flood",
                "location": {"lng": -118.0 + i * 0.1, "lat": 34.0},
                "radius_meters": 500,
            },
        )
    resp = client.get("/api/v1/hazards/active")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_delete_hazard() -> None:
    _clear_store()
    resp = client.post(
        "/api/v1/hazards/report",
        json={
            "hazard_type": "roadblock",
            "location": {"lng": -118.3, "lat": 34.1},
        },
    )
    hazard_id = resp.json()["hazard_id"]

    del_resp = client.delete(f"/api/v1/hazards/{hazard_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deactivated"

    # Should no longer appear in active
    active = client.get("/api/v1/hazards/active").json()
    assert len(active) == 0


def test_delete_nonexistent_hazard() -> None:
    _clear_store()
    resp = client.delete("/api/v1/hazards/nonexistent-id")
    assert resp.status_code == 404
