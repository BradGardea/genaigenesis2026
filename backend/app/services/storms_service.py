"""Storms service — orchestrates provider calls and returns typed storm models.

Flow:
    route → storms_service → [nhc | jtwc | ibtracs] providers
          → storm_normalization helpers → schema response models

Design principles:
  - NHC is the primary source for Atlantic/East-Pacific storms.
  - JTWC is merged in for West-Pacific/Indian Ocean/Southern Hemisphere.
  - Provider failures are isolated; missing data produces empty/null fields,
    not 500 errors.
  - Geometry (advisory GeoJSON) is a best-effort fetch; None is a valid result.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from app.providers import nhc, jtwc
from app.schemas.storm_models import (
    ActiveStormsResponse,
    ActiveStormItem,
    StormDetail,
    StormTrackResponse,
    StormTrackPoint,
    StormGeometrySnapshot,
    StormForecastResponse,
)
from app.utils.storm_normalization import (
    nhc_to_active_storm,
    nhc_to_storm_detail,
    nhc_raw_track_to_points,
    nhc_raw_forecast_to_points,
    parse_nhc_wind_radii,
)
from app.utils.time import utcnow_iso

_HTTP_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Active storms list
# ---------------------------------------------------------------------------


async def get_active_storms() -> ActiveStormsResponse:
    """Return all active tropical storms from NHC and JTWC combined.

    NHC covers AL/EP/CP basins; JTWC covers WP/IO/SH basins.
    Both are fetched concurrently. Any provider that fails returns an
    empty contribution without aborting the response.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        nhc_raw, jtwc_raw = await asyncio.gather(
            nhc.fetch_active_storms(client),
            jtwc.fetch_active_storms(client),
        )

    storms: list[ActiveStormItem] = []

    for raw in nhc_raw:
        item = nhc_to_active_storm(raw)
        if item:
            storms.append(item)

    # JTWC entries carry minimal fields; reuse the same normalization helper
    # since the raw dict keys are the same format we produce in jtwc.py.
    for raw in jtwc_raw:
        item = nhc_to_active_storm(raw)
        if item:
            item.source = "jtwc"
            storms.append(item)

    # Deduplicate by storm_id in case a storm appears in both feeds
    seen: set[str] = set()
    unique: list[ActiveStormItem] = []
    for s in storms:
        if s.storm_id not in seen:
            seen.add(s.storm_id)
            unique.append(s)

    note = (
        "NHC covers Atlantic/East-Pacific. "
        "JTWC covers West-Pacific/Indian Ocean/Southern Hemisphere. "
        "May be empty outside active storm season."
    )

    return ActiveStormsResponse(
        storms=unique,
        count=len(unique),
        fetched_at=utcnow_iso(),
        note=note,
    )


# ---------------------------------------------------------------------------
# Storm detail
# ---------------------------------------------------------------------------


async def get_storm_detail(storm_id: str) -> Optional[StormDetail]:
    """Return full detail for a single active storm by ID.

    Searches NHC first; falls back to JTWC if not found.
    Returns None if the storm is not currently active in either provider.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        raw = await nhc.fetch_storm_by_id(client, storm_id)
        if raw:
            return nhc_to_storm_detail(raw)

        # Try JTWC if NHC didn't have it
        jtwc_storms = await jtwc.fetch_active_storms(client)

    needle = storm_id.lower()
    for s in jtwc_storms:
        sid = str(s.get("id") or "").lower()
        if sid == needle:
            detail = nhc_to_storm_detail(s)
            if detail:
                detail.source = "jtwc"
            return detail

    return None


# ---------------------------------------------------------------------------
# Storm track
# ---------------------------------------------------------------------------


async def get_storm_track(storm_id: str) -> StormTrackResponse:
    """Return the observed or forecast track for a storm.

    The NHC CurrentStorms.json sometimes embeds a 'forecastTrack' array
    with the official 5-day forecast positions. We surface those here as
    the best available track. Historical positions are not yet wired in
    (IBTrACS integration is a TODO in ibtracs.py).

    Always returns a StormTrackResponse; the track list may be empty.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        raw = await nhc.fetch_storm_by_id(client, storm_id)

    name = "UNKNOWN"
    track_points: list[StormTrackPoint] = []
    note: Optional[str] = None

    if raw:
        name = str(raw.get("name") or "UNNAMED").upper()
        # Current position as the first track point
        lat = raw.get("latitudeNumeric") or _parse_coord(raw.get("latitude"), "lat")
        lon = raw.get("longitudeNumeric") or _parse_coord(raw.get("longitude"), "lon")
        if lat is not None and lon is not None:
            track_points.append(
                StormTrackPoint(
                    time=str(raw.get("lastUpdate") or utcnow_iso()),
                    latitude=float(lat),
                    longitude=float(lon),
                    max_wind_kt=_safe_int(raw.get("intensity") or raw.get("maxWind")),
                    min_pressure_mb=_safe_float(raw.get("pressure")),
                    classification=str(raw.get("classification") or "TD").upper(),
                )
            )

        # Append forecast track points if the provider includes them
        raw_forecast = raw.get("forecastTrack") or raw.get("forecast_track") or []
        if isinstance(raw_forecast, list):
            track_points.extend(nhc_raw_track_to_points(raw_forecast))

        if len(track_points) <= 1:
            note = (
                "Only the current position is available. "
                "Historical best-track data requires IBTrACS integration (ibtracs.py TODO)."
            )
    else:
        note = f"Storm '{storm_id}' not found in active NHC feed."

    return StormTrackResponse(
        storm_id=storm_id.lower(),
        name=name,
        source="nhc",
        track=track_points,
        note=note,
    )


# ---------------------------------------------------------------------------
# Storm geometry
# ---------------------------------------------------------------------------


async def get_storm_geometry(storm_id: str) -> StormGeometrySnapshot:
    """Return the current geometry snapshot: center position + wind radii rings.

    Attempts to fetch the NHC advisory GeoJSON for the 5-day forecast cone.
    If the advisory GeoJSON is unavailable, cone_geojson will be None and
    only the current position and wind radii (from CurrentStorms.json) are
    returned.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        raw, advisory_geojson = await asyncio.gather(
            nhc.fetch_storm_by_id(client, storm_id),
            nhc.fetch_advisory_geojson(client, storm_id),
        )

    if raw is None:
        # Return a minimal snapshot so the endpoint always returns 200
        return StormGeometrySnapshot(
            storm_id=storm_id.lower(),
            name="UNKNOWN",
            valid_time=utcnow_iso(),
            center_latitude=0.0,
            center_longitude=0.0,
            source="nhc",
            note=f"Storm '{storm_id}' not found in active NHC feed.",
        )

    name = str(raw.get("name") or "UNNAMED").upper()
    lat = raw.get("latitudeNumeric") or _parse_coord(raw.get("latitude"), "lat") or 0.0
    lon = raw.get("longitudeNumeric") or _parse_coord(raw.get("longitude"), "lon") or 0.0
    valid_time = str(raw.get("lastUpdate") or utcnow_iso())

    wind_radii = parse_nhc_wind_radii(raw)

    note: Optional[str] = None
    if advisory_geojson is None:
        note = (
            "Advisory GeoJSON (5-day cone) is not currently available from NHC. "
            "cone_geojson will be populated when the NHC publishes an active advisory."
        )

    return StormGeometrySnapshot(
        storm_id=storm_id.lower(),
        name=name,
        valid_time=valid_time,
        center_latitude=float(lat),
        center_longitude=float(lon),
        wind_radii=wind_radii,
        cone_geojson=advisory_geojson,
        source="nhc",
        note=note,
    )


# ---------------------------------------------------------------------------
# Storm forecast
# ---------------------------------------------------------------------------


async def get_storm_forecast(storm_id: str) -> StormForecastResponse:
    """Return the official 5-day forecast track for a storm.

    Extracts forecast points from the NHC CurrentStorms.json 'forecastTrack'
    array. Also attempts to attach the advisory GeoJSON cone polygon when
    available from the NHC advisory GeoJSON endpoint.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        raw, advisory_geojson = await asyncio.gather(
            nhc.fetch_storm_by_id(client, storm_id),
            nhc.fetch_advisory_geojson(client, storm_id),
        )

    if raw is None:
        return StormForecastResponse(
            storm_id=storm_id.lower(),
            name="UNKNOWN",
            source="nhc",
            note=f"Storm '{storm_id}' not found in active NHC feed.",
        )

    name = str(raw.get("name") or "UNNAMED").upper()

    raw_forecast = raw.get("forecastTrack") or raw.get("forecast_track") or []
    forecast_points = nhc_raw_forecast_to_points(
        raw_forecast if isinstance(raw_forecast, list) else []
    )

    note: Optional[str] = None
    if not forecast_points:
        note = (
            "No forecast track points were embedded in the NHC CurrentStorms feed "
            "for this storm. NHC may not have issued an advisory yet."
        )

    return StormForecastResponse(
        storm_id=storm_id.lower(),
        name=name,
        source="nhc",
        forecast_points=forecast_points,
        cone_geojson=advisory_geojson,
        note=note,
    )


# ---------------------------------------------------------------------------
# Private helpers (local to service, not re-exported)
# ---------------------------------------------------------------------------


def _parse_coord(value: object, kind: str) -> Optional[float]:
    """Thin delegation to normalization helpers without importing them in routes."""
    from app.utils.storm_normalization import parse_nhc_lat, parse_nhc_lon
    return parse_nhc_lat(value) if kind == "lat" else parse_nhc_lon(value)


def _safe_int(v: object) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(v: object) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
