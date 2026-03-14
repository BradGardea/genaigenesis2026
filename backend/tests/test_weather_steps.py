from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_weather_current_step_returns_metadata_and_cards() -> None:
    response = client.get("/api/v1/information/weather/current-step", params={"step": 0})
    assert response.status_code == 200
    payload = response.json()

    assert payload["metadata"]["dataset_name"] == "goma_severe_storm_12h_10min_mock"
    assert payload["step"]["step_index"] == 0
    assert payload["step"]["has_next"] is True
    assert isinstance(payload["beautified"], list)
    assert len(payload["beautified"]) > 0
    assert "raw" in payload


def test_get_weather_next_step_advances_index() -> None:
    response = client.get("/api/v1/information/weather/next-step", params={"curr_step": 0})
    assert response.status_code == 200
    payload = response.json()
    assert payload["step"]["step_index"] == 1
