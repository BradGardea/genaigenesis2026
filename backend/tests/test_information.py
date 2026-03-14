from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_information_endpoints_available() -> None:
    alerts = client.get("/api/v1/information/alerts")
    assert alerts.status_code == 200
    assert isinstance(alerts.json(), list)
    assert len(alerts.json()) > 0

    plans = client.get("/api/v1/information/evacuation-plans")
    assert plans.status_code == 200
    payload = plans.json()
    assert len(payload) > 0
    assert payload[0]["successProbability"] >= payload[-1]["successProbability"]


def test_create_connection_creates_reciprocal() -> None:
    body = {
        "ownerPhone": "(555) 010-2030",
        "contactPhone": "(555) 010-7777",
        "relationship": "dependent",
    }

    response = client.post("/api/v1/information/connections", json=body)
    assert response.status_code == 200

    payload = response.json()
    assert payload["primary"]["relationship"] == "dependent"
    assert payload["primary"]["trustLevel"] == 3
    assert payload["reciprocal"]["relationship"] == "guardian"
    assert payload["reciprocal"]["trustLevel"] == 3

    owner_connections = client.get(
        "/api/v1/information/connections",
        params={"owner_phone": "(555) 010-2030"},
    )
    assert owner_connections.status_code == 200
    owner_payload = owner_connections.json()
    assert any(connection["contactPhone"] == "(555) 010-7777" for connection in owner_payload)
