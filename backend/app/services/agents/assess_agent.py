"""Agent 1 — Disaster Assessment.

Consumes weather step + city-state step data to produce a unified
DisasterAssessmentOutput with unsafe zones, storm movement, and alerts.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone

from app.schemas.agent_models import (
    ActiveAlert,
    AssessRequest,
    DisasterAssessmentOutput,
    LatLon,
    ScenarioSnapshot,
    StormMovement,
    UnsafeZone,
)
from app.services import city_state_steps_service, storms_service, weather_steps_service

logger = logging.getLogger(__name__)


def _circle_polygon(lat: float, lon: float, radius_m: float, n: int = 16) -> dict:
    """Generate a GeoJSON Polygon approximating a circle."""
    coords = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        dlat = (radius_m * math.sin(angle)) / 111_320.0
        dlon = (radius_m * math.cos(angle)) / max(111_320.0 * math.cos(math.radians(lat)), 1e-6)
        coords.append([round(lon + dlon, 6), round(lat + dlat, 6)])
    coords.append(coords[0])  # close ring
    return {"type": "Polygon", "coordinates": [coords]}


def _danger_from_severity(severity: int) -> str:
    if severity >= 85:
        return "extreme"
    if severity >= 65:
        return "high"
    if severity >= 35:
        return "moderate"
    return "low"


async def run_assessment(request: AssessRequest) -> DisasterAssessmentOutput:
    """Execute Agent 1: build unsafe zones from city-state + storm data."""
    assessment_id = f"assess-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    # ── Fetch city-state step ─────────────────────────────────
    city_resp = None
    try:
        city_resp = await city_state_steps_service.get_city_state_current_step(
            request.city_state_step_index, beautify=False,
        )
    except Exception:
        logger.warning("Failed to fetch city-state step %d", request.city_state_step_index)

    # ── Fetch weather step (for step_time) ────────────────────
    weather_resp = None
    try:
        weather_resp = await weather_steps_service.get_weather_current_step(
            request.weather_step_index, beautify=False,
        )
    except Exception:
        logger.warning("Failed to fetch weather step %d", request.weather_step_index)

    step_time = ""
    if weather_resp:
        step_time = weather_resp.step.step_time

    # ── Build scenario snapshot ───────────────────────────────
    overall_severity = 0
    operational_status = "unknown"
    dominant_impacts: list[str] = []
    affected_areas: list[dict] = []

    if city_resp:
        raw_cs = city_resp.raw.get("city_state", {})
        overall_severity = int(raw_cs.get("overall_severity", 0))
        operational_status = str(raw_cs.get("operational_status", "unknown"))
        dominant_impacts = raw_cs.get("dominant_impacts", [])
        affected_areas = raw_cs.get("affected_areas", [])

    scenario = ScenarioSnapshot(
        step_index=request.city_state_step_index,
        step_time=step_time,
        overall_severity=overall_severity,
        operational_status=operational_status,
        dominant_impacts=dominant_impacts,
    )

    # ── Unsafe zones from city_state affected_areas ───────────
    unsafe_zones: list[UnsafeZone] = []
    for idx, area in enumerate(affected_areas):
        impact_type = str(area.get("impact_type", ""))
        severity = int(area.get("severity", 0))
        if severity < 30:
            continue
        lat = float(area.get("lat", 0))
        lon = float(area.get("lon", 0))
        radius_m = int(area.get("radius_m", 150))
        unsafe_zones.append(UnsafeZone(
            zone_id=f"zone-city-{idx}",
            source="city_state",
            impact_type=impact_type,
            danger_to_remain=area.get("danger_to_remain", _danger_from_severity(severity)),
            severity=severity,
            valid_from=step_time,
            valid_until="",
            center=LatLon(lat=lat, lon=lon),
            radius_m=radius_m,
            polygon=_circle_polygon(lat, lon, radius_m),
        ))

    # ── Fetch storms for storm_focus + storm_forecast zones ───
    storm_movement: StormMovement | None = None
    try:
        storms_resp = await storms_service.get_active_storms()
        for storm in storms_resp.storms:
            if storm.latitude is None or storm.longitude is None:
                continue

            # Storm focus zone (current position)
            radius_m = 5000
            unsafe_zones.append(UnsafeZone(
                zone_id=f"zone-focus-{storm.storm_id}",
                source="storm_focus",
                impact_type=storm.classification.lower(),
                danger_to_remain="high" if (storm.intensity_kt or 0) >= 50 else "moderate",
                severity=min(100, (storm.intensity_kt or 30) + 20),
                valid_from=storm.last_update or now,
                valid_until="",
                center=LatLon(lat=storm.latitude, lon=storm.longitude),
                radius_m=radius_m,
                polygon=_circle_polygon(storm.latitude, storm.longitude, radius_m),
            ))

            # Storm forecast zones
            try:
                forecast_resp = await storms_service.get_storm_forecast(storm.storm_id)
                for fp_idx, fp in enumerate(forecast_resp.forecast_points[:2]):
                    # Use wind radii if available, else default
                    fp_radius = 22400
                    if fp.wind_radii:
                        r34 = next((r for r in fp.wind_radii if r.wind_speed_kt == 34), None)
                        if r34 and r34.ne_km:
                            fp_radius = int(r34.ne_km * 1000)

                    label = "30min" if fp_idx == 0 else "60min"
                    unsafe_zones.append(UnsafeZone(
                        zone_id=f"zone-forecast-{label}",
                        source="storm_forecast",
                        impact_type="storm_track",
                        danger_to_remain="high",
                        severity=min(100, (fp.max_wind_kt or 30) + 20),
                        valid_from=fp.valid_time,
                        valid_until="",
                        center=LatLon(lat=fp.latitude, lon=fp.longitude),
                        radius_m=fp_radius,
                        polygon=_circle_polygon(fp.latitude, fp.longitude, fp_radius),
                    ))

                # Build storm_movement from first storm found
                if storm_movement is None:
                    forecast_30 = None
                    forecast_60 = None
                    if len(forecast_resp.forecast_points) >= 1:
                        fp0 = forecast_resp.forecast_points[0]
                        forecast_30 = LatLon(lat=fp0.latitude, lon=fp0.longitude)
                    if len(forecast_resp.forecast_points) >= 2:
                        fp1 = forecast_resp.forecast_points[1]
                        forecast_60 = LatLon(lat=fp1.latitude, lon=fp1.longitude)

                    speed_kmh = None
                    if storm.movement_speed_kt is not None:
                        speed_kmh = round(storm.movement_speed_kt * 1.852, 1)

                    storm_movement = StormMovement(
                        direction_deg=storm.movement_dir_deg,
                        speed_kmh=speed_kmh,
                        current_center=LatLon(lat=storm.latitude, lon=storm.longitude),
                        forecast_30min=forecast_30,
                        forecast_60min=forecast_60,
                        wind_speed_kmh=round((storm.intensity_kt or 0) * 1.852, 1) if storm.intensity_kt else None,
                        rainfall_mm_10min=None,
                    )
            except Exception:
                logger.debug("Failed to fetch storm forecast for %s", storm.storm_id)
    except Exception:
        logger.debug("Failed to fetch active storms")

    # ── Active alerts from city-state response ────────────────
    active_alerts: list[ActiveAlert] = []
    if city_resp:
        for alert in city_resp.alerts:
            active_alerts.append(ActiveAlert(
                id=alert.id,
                title=alert.title,
                urgency=alert.urgency,
                category=alert.category,
                area=alert.area,
                source=alert.source,
            ))

    total = len(unsafe_zones)
    dominant_str = ", ".join(dominant_impacts) if dominant_impacts else "mixed impacts"
    summary = (
        f"{total} unsafe zones identified at step {request.city_state_step_index}. "
        f"Dominant hazards: {dominant_str}. Overall severity: {overall_severity}/100."
    )

    return DisasterAssessmentOutput(
        assessment_id=assessment_id,
        generated_at=now,
        scenario=scenario,
        unsafe_zones=unsafe_zones,
        storm_movement=storm_movement,
        active_alerts=active_alerts,
        total_unsafe_zones=total,
        summary=summary,
    )
