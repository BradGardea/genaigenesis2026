"""Tests for the /storms/* endpoints.

Uses unittest.mock to patch provider HTTP calls so tests are fast and
offline-safe. The mock responses exercise both the happy path and the
various null/missing-field edge cases that real NHC payloads can produce.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared mock NHC payloads
# ---------------------------------------------------------------------------

MOCK_STORM_ALPHA = {
    "id": "al012025",
    "name": "ALPHA",
    "classification": "HU",
    "intensity": 90,
    "pressure": 965,
    "headline": "HURRICANE ALPHA APPROACHING THE COAST",
    "latitudeNumeric": 25.5,
    "longitudeNumeric": -80.2,
    "movementDir": 315,
    "movementSpeed": 12,
    "lastUpdate": "2025-08-01T12:00:00Z",
    "publicAdvisory": {
        "number": "015",
        "issued": "2025-08-01T12:00:00Z",
        "url": "https://www.nhc.noaa.gov/text/MIATCPAT1.shtml",
    },
    "forecastAdvisory": {
        "number": "015A",
        "issued": "2025-08-01T12:00:00Z",
        "url": "https://www.nhc.noaa.gov/text/MIATCMAT1.shtml",
    },
    "initialWindRadii": {
        "34kt": {"NE": 200, "SE": 180, "SW": 120, "NW": 150},
        "50kt": {"NE": 90, "SE": 80, "SW": 60, "NW": 70},
        "64kt": {"NE": 30, "SE": 25, "SW": 0, "NW": 0},
    },
    "forecastTrack": [
        {
            "validTime": "2025-08-02T00:00:00Z",
            "latitudeNumeric": 26.8,
            "longitudeNumeric": -81.5,
            "maxWind": 100,
            "minPressure": 955,
            "classification": "HU",
        },
        {
            "validTime": "2025-08-02T12:00:00Z",
            "latitudeNumeric": 28.1,
            "longitudeNumeric": -82.3,
            "maxWind": 85,
            "minPressure": 970,
            "classification": "HU",
        },
    ],
}

MOCK_STORM_BETA_MINIMAL = {
    # Minimal fields — exercises missing-field handling
    "id": "ep022025",
    "name": "BETA",
    "classification": "TS",
    # No numeric lat/lon — uses string form
    "latitude": "15.3N",
    "longitude": "105.7W",
    # No intensity, pressure, movement, radii, or forecast track
}

MOCK_NHC_TWO_STORMS = [MOCK_STORM_ALPHA, MOCK_STORM_BETA_MINIMAL]


# ---------------------------------------------------------------------------
# Helper: patch both provider fetches
# ---------------------------------------------------------------------------


def _patch_nhc_storms(return_value: list) -> "patch":
    return patch(
        "app.providers.nhc.fetch_active_storms",
        new=AsyncMock(return_value=return_value),
    )


def _patch_jtwc_storms(return_value: list = None) -> "patch":
    return patch(
        "app.providers.jtwc.fetch_active_storms",
        new=AsyncMock(return_value=return_value or []),
    )


def _patch_nhc_by_id(return_value) -> "patch":
    return patch(
        "app.providers.nhc.fetch_storm_by_id",
        new=AsyncMock(return_value=return_value),
    )


def _patch_nhc_advisory_geojson(return_value) -> "patch":
    return patch(
        "app.providers.nhc.fetch_advisory_geojson",
        new=AsyncMock(return_value=return_value),
    )


# ---------------------------------------------------------------------------
# /storms/active
# ---------------------------------------------------------------------------


def test_active_storms_returns_two_storms() -> None:
    """Active storms endpoint merges NHC results into a typed response."""
    with _patch_nhc_storms(MOCK_NHC_TWO_STORMS), _patch_jtwc_storms():
        r = client.get("/api/v1/storms/active")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert len(body["storms"]) == 2

    # First storm should have full detail
    alpha = next(s for s in body["storms"] if s["storm_id"] == "al012025")
    assert alpha["name"] == "ALPHA"
    assert alpha["classification"] == "HU"
    assert alpha["intensity_kt"] == 90
    assert alpha["latitude"] == pytest.approx(25.5)
    assert alpha["source"] == "nhc"

    # Second storm uses string lat/lon — should still be parsed
    beta = next(s for s in body["storms"] if s["storm_id"] == "ep022025")
    assert beta["name"] == "BETA"
    assert beta["intensity_kt"] is None  # not provided


def test_active_storms_empty_providers() -> None:
    """Active storms returns empty list when both providers return nothing."""
    with _patch_nhc_storms([]), _patch_jtwc_storms([]):
        r = client.get("/api/v1/storms/active")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["storms"] == []
    assert body["note"] is not None


def test_active_storms_deduplicates() -> None:
    """If the same storm_id appears in both NHC and JTWC, it is deduplicated."""
    dup = {**MOCK_STORM_ALPHA, "source": "jtwc"}
    with _patch_nhc_storms([MOCK_STORM_ALPHA]), _patch_jtwc_storms([dup]):
        r = client.get("/api/v1/storms/active")
    assert r.status_code == 200
    assert r.json()["count"] == 1


# ---------------------------------------------------------------------------
# /storms/{storm_id}
# ---------------------------------------------------------------------------


def test_storm_detail_found() -> None:
    """Storm detail endpoint returns full record for a known storm."""
    with _patch_nhc_by_id(MOCK_STORM_ALPHA):
        r = client.get("/api/v1/storms/al012025")
    assert r.status_code == 200
    body = r.json()
    assert body["storm_id"] == "al012025"
    assert body["name"] == "ALPHA"
    assert body["intensity_kt"] == 90
    assert body["public_advisory_url"] is not None
    # Wind radii should be present (34, 50, 64 kt)
    radii = body["current_wind_radii"]
    assert len(radii) == 3
    kt_values = {r["wind_speed_kt"] for r in radii}
    assert kt_values == {34, 50, 64}


def test_storm_detail_not_found() -> None:
    """Storm detail returns 404 for an unknown storm ID."""
    with _patch_nhc_by_id(None), _patch_jtwc_storms([]):
        r = client.get("/api/v1/storms/xx999999")
    assert r.status_code == 404
    assert "not currently active" in r.json()["detail"]


def test_storm_detail_missing_fields() -> None:
    """Storm detail handles a minimal storm payload without crashing."""
    with _patch_nhc_by_id(MOCK_STORM_BETA_MINIMAL):
        r = client.get("/api/v1/storms/ep022025")
    assert r.status_code == 200
    body = r.json()
    assert body["intensity_kt"] is None
    assert body["pressure_mb"] is None
    assert body["current_wind_radii"] == []


# ---------------------------------------------------------------------------
# /storms/{storm_id}/track
# ---------------------------------------------------------------------------


def test_storm_track_includes_current_and_forecast() -> None:
    """Track endpoint prepends current position and appends forecast points."""
    with _patch_nhc_by_id(MOCK_STORM_ALPHA):
        r = client.get("/api/v1/storms/al012025/track")
    assert r.status_code == 200
    body = r.json()
    assert body["storm_id"] == "al012025"
    # 1 current position + 2 forecast points
    assert len(body["track"]) == 3
    assert body["track"][0]["latitude"] == pytest.approx(25.5)
    assert body["track"][1]["latitude"] == pytest.approx(26.8)


def test_storm_track_unknown_storm() -> None:
    """Track endpoint for unknown storm returns 200 with empty track and note."""
    with _patch_nhc_by_id(None):
        r = client.get("/api/v1/storms/xx999999/track")
    assert r.status_code == 200
    body = r.json()
    assert body["track"] == []
    assert body["note"] is not None
    assert "not found" in body["note"]


# ---------------------------------------------------------------------------
# /storms/{storm_id}/geometry
# ---------------------------------------------------------------------------


def test_storm_geometry_with_no_advisory_geojson() -> None:
    """Geometry endpoint returns wind radii and null cone when GeoJSON unavailable."""
    with _patch_nhc_by_id(MOCK_STORM_ALPHA), _patch_nhc_advisory_geojson(None):
        r = client.get("/api/v1/storms/al012025/geometry")
    assert r.status_code == 200
    body = r.json()
    assert body["center_latitude"] == pytest.approx(25.5)
    assert body["center_longitude"] == pytest.approx(-80.2)
    assert body["cone_geojson"] is None
    assert len(body["wind_radii"]) == 3
    # NE quadrant of 34-kt ring: 200 nm * 1.852 = 370.4 km
    ring34 = next(r for r in body["wind_radii"] if r["wind_speed_kt"] == 34)
    assert ring34["ne_km"] == pytest.approx(200 * 1.852, abs=0.1)


def test_storm_geometry_with_advisory_geojson() -> None:
    """Geometry endpoint attaches cone_geojson when provider returns it."""
    mock_cone = {"type": "FeatureCollection", "features": []}
    with _patch_nhc_by_id(MOCK_STORM_ALPHA), _patch_nhc_advisory_geojson(mock_cone):
        r = client.get("/api/v1/storms/al012025/geometry")
    assert r.status_code == 200
    assert r.json()["cone_geojson"] == mock_cone


def test_storm_geometry_unknown_storm() -> None:
    """Geometry endpoint returns 200 with placeholder coords for unknown storm."""
    with _patch_nhc_by_id(None), _patch_nhc_advisory_geojson(None):
        r = client.get("/api/v1/storms/xx999999/geometry")
    assert r.status_code == 200
    body = r.json()
    assert body["storm_id"] == "xx999999"
    assert body["name"] == "UNKNOWN"
    assert "not found" in (body["note"] or "")


# ---------------------------------------------------------------------------
# /storms/{storm_id}/forecast
# ---------------------------------------------------------------------------


def test_storm_forecast_returns_points() -> None:
    """Forecast endpoint returns typed forecast points with intensity fields."""
    with _patch_nhc_by_id(MOCK_STORM_ALPHA), _patch_nhc_advisory_geojson(None):
        r = client.get("/api/v1/storms/al012025/forecast")
    assert r.status_code == 200
    body = r.json()
    assert body["storm_id"] == "al012025"
    assert len(body["forecast_points"]) == 2
    assert body["forecast_points"][0]["max_wind_kt"] == 100
    assert body["forecast_points"][0]["classification"] == "HU"


def test_storm_forecast_empty_when_no_track() -> None:
    """Forecast is empty with explanatory note when provider has no forecastTrack."""
    storm_no_track = {k: v for k, v in MOCK_STORM_ALPHA.items() if k != "forecastTrack"}
    with _patch_nhc_by_id(storm_no_track), _patch_nhc_advisory_geojson(None):
        r = client.get("/api/v1/storms/al012025/forecast")
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_points"] == []
    assert body["note"] is not None
