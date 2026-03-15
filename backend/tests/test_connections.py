from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_first_person_connections_are_step_aware() -> None:
    initial_response = client.get("/api/v1/connections/first", params={"step": 0})
    assert initial_response.status_code == 200
    initial_payload = initial_response.json()
    assert initial_payload["step_index"] == 0
    assert all(node["emergency_event"] is None for node in initial_payload["connections"])

    escalated_response = client.get("/api/v1/connections/first", params={"step": 5})
    assert escalated_response.status_code == 200
    escalated_payload = escalated_response.json()
    assert escalated_payload["step_index"] == 5

    help_needed = [
        node for node in escalated_payload["connections"] if node["emergency_event"] is not None
    ]
    assert len(help_needed) == 1
    assert help_needed[0]["person"]["name"] == "Karen Moore"
    assert help_needed[0]["person"]["scenario"] == "Needs a ride to evacuate"
    assert help_needed[0]["emergency_event"]["event_type"] == "needs_help"
    assert help_needed[0]["emergency_event"]["active"] is True
    assert help_needed[0]["emergency_event"]["activated_at_step"] == 5


def test_help_needed_endpoint_returns_active_connection_only() -> None:
    response = client.get("/api/v1/connections/help-needed", params={"step": 5})
    assert response.status_code == 200

    payload = response.json()
    assert payload["step_index"] == 5
    assert payload["focal_person"]["name"] == "Cristina Net"
    assert len(payload["help_needed"]) == 1
    assert payload["help_needed"][0]["person"]["name"] == "Karen Moore"
