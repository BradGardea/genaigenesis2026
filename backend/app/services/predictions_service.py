"""Predictions service — heuristic hazard risk scoring.

Combines active alert signals with near-term weather forecast drivers to
produce explainable, heuristic risk assessments for wildfire spread, flood,
and severe weather hazards.

IMPORTANT: These are NOT scientifically certified forecasts. They are
transparency-first, heuristic estimates intended for situational awareness.
Always defer to official government warnings.
"""

import asyncio
from typing import List

import httpx

from app.schemas.prediction_models import HazardPrediction, PredictionSummary
from app.schemas.alert_models import AlertSignal
from app.services.alerts_service import fetch_all_signals
from app.providers import open_meteo
from app.utils.geo import filter_signals_near
from app.utils.time import utcnow_iso, hours_from_now_iso


# --------------------------------------------------------------------------
# Scoring configuration
# --------------------------------------------------------------------------

WILDFIRE_RADIUS_KM = 300.0
FLOOD_RADIUS_KM = 400.0
SEVERE_WEATHER_RADIUS_KM = 400.0

# Thresholds for risk level assignment
SCORE_MEDIUM_THRESHOLD = 30
SCORE_HIGH_THRESHOLD = 60


def _score_to_risk(score: int) -> str:
    if score >= SCORE_HIGH_THRESHOLD:
        return "high"
    if score >= SCORE_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _score_to_confidence(drivers_count: int) -> str:
    """Confidence increases with the number of independent data sources used."""
    if drivers_count >= 3:
        return "medium"
    return "low"


# --------------------------------------------------------------------------
# Wildfire spread risk scoring
# --------------------------------------------------------------------------

def _score_wildfire(
    nearby: List[AlertSignal],
    hourly_data: dict,
) -> tuple[int, List[str], List[str]]:
    """Compute a 0-100 wildfire spread risk score.

    Returns (score, drivers, based_on).
    Drivers are plain-language explanations for each factor.
    Based_on lists the data sources consulted.
    """
    score = 0
    drivers: List[str] = []
    based_on: List[str] = []

    # Active fire detections in the area
    fire_signals = [s for s in nearby if s.signal_type == "wildfire"]
    if fire_signals:
        score += 35
        drivers.append(
            f"{len(fire_signals)} active wildfire detection(s) within "
            f"{WILDFIRE_RADIUS_KM:.0f} km"
        )
        based_on.extend(list({s.source for s in fire_signals}))

    hourly = hourly_data.get("hourly", {})

    # Wind speed — accelerates fire spread
    wind_speeds: List[float] = [
        v for v in hourly.get("wind_speed_10m", [])[:24] if v is not None
    ]
    if wind_speeds:
        max_wind = max(wind_speeds)
        based_on.append("open-meteo")
        if max_wind >= 50:
            score += 25
            drivers.append(f"High wind speeds forecast (up to {max_wind:.0f} km/h)")
        elif max_wind >= 30:
            score += 15
            drivers.append(f"Elevated wind speeds forecast (up to {max_wind:.0f} km/h)")
        elif max_wind >= 15:
            score += 5
            drivers.append(f"Moderate wind speeds forecast (up to {max_wind:.0f} km/h)")

    # Temperature — hot conditions dry vegetation
    temps: List[float] = [
        v for v in hourly.get("temperature_2m", [])[:24] if v is not None
    ]
    if temps:
        max_temp = max(temps)
        if max_temp >= 38:
            score += 20
            drivers.append(f"Very high temperature forecast ({max_temp:.1f}°C)")
        elif max_temp >= 30:
            score += 10
            drivers.append(f"Elevated temperature forecast ({max_temp:.1f}°C)")

    # Relative humidity — low humidity increases ignition / spread potential
    humidities: List[float] = [
        v for v in hourly.get("relative_humidity_2m", [])[:24] if v is not None
    ]
    if humidities:
        min_rh = min(humidities)
        if min_rh <= 20:
            score += 20
            drivers.append(f"Very low relative humidity forecast (min {min_rh:.0f}%)")
        elif min_rh <= 35:
            score += 10
            drivers.append(f"Low relative humidity forecast (min {min_rh:.0f}%)")

    if not drivers:
        drivers.append("No significant wildfire risk factors detected in available data.")

    return min(score, 100), drivers, list(set(based_on))


# --------------------------------------------------------------------------
# Flood risk scoring
# --------------------------------------------------------------------------

def _score_flood(
    nearby: List[AlertSignal],
    hourly_data: dict,
) -> tuple[int, List[str], List[str]]:
    """Compute a 0-100 flood risk score."""
    score = 0
    drivers: List[str] = []
    based_on: List[str] = []

    # Active flood-related alerts in the area
    flood_signals = [
        s
        for s in nearby
        if s.signal_type == "flood" or "flood" in (s.value or "").lower()
    ]
    if flood_signals:
        score += 40
        drivers.append(
            f"{len(flood_signals)} active flood-related alert(s) within "
            f"{FLOOD_RADIUS_KM:.0f} km"
        )
        based_on.extend(list({s.source for s in flood_signals}))

    # Other severe / extreme alerts in the area
    severe_signals = [
        s for s in nearby if s.severity in ("extreme", "severe") and s not in flood_signals
    ]
    if severe_signals:
        score += 15
        drivers.append(
            f"{len(severe_signals)} additional severe weather alert(s) in area"
        )

    hourly = hourly_data.get("hourly", {})

    # Precipitation probability — high probability increases flood likelihood
    precip_probs: List[int] = [
        v for v in hourly.get("precipitation_probability", [])[:48] if v is not None
    ]
    if precip_probs:
        max_prob = max(precip_probs)
        based_on.append("open-meteo")
        if max_prob >= 80:
            score += 30
            drivers.append(f"Very high precipitation probability forecast (up to {max_prob}%)")
        elif max_prob >= 60:
            score += 20
            drivers.append(f"High precipitation probability forecast (up to {max_prob}%)")
        elif max_prob >= 40:
            score += 10
            drivers.append(f"Moderate precipitation probability forecast (up to {max_prob}%)")

    if not drivers:
        drivers.append("No significant flood risk factors detected in available data.")

    return min(score, 100), drivers, list(set(based_on))


# --------------------------------------------------------------------------
# Severe weather risk scoring
# --------------------------------------------------------------------------

def _score_severe_weather(
    nearby: List[AlertSignal],
    hourly_data: dict,
) -> tuple[int, List[str], List[str]]:
    """Compute a 0-100 severe weather risk score."""
    score = 0
    drivers: List[str] = []
    based_on: List[str] = []

    # Active severe or extreme alerts in area
    severe_alerts = [
        s for s in nearby if s.severity in ("extreme", "severe") or s.source == "noaa-nws"
    ]
    if severe_alerts:
        score += 35
        drivers.append(
            f"{len(severe_alerts)} severe/extreme weather alert(s) within "
            f"{SEVERE_WEATHER_RADIUS_KM:.0f} km"
        )
        based_on.extend(list({s.source for s in severe_alerts}))

    hourly = hourly_data.get("hourly", {})

    # Wind speed — high winds are a direct severe weather indicator
    wind_speeds: List[float] = [
        v for v in hourly.get("wind_speed_10m", [])[:24] if v is not None
    ]
    if wind_speeds:
        max_wind = max(wind_speeds)
        based_on.append("open-meteo")
        if max_wind >= 80:
            score += 30
            drivers.append(f"Very high wind speeds forecast (up to {max_wind:.0f} km/h)")
        elif max_wind >= 50:
            score += 20
            drivers.append(f"High wind speeds forecast (up to {max_wind:.0f} km/h)")
        elif max_wind >= 30:
            score += 10
            drivers.append(f"Elevated wind speeds forecast (up to {max_wind:.0f} km/h)")

    # Precipitation probability
    precip_probs: List[int] = [
        v for v in hourly.get("precipitation_probability", [])[:24] if v is not None
    ]
    if precip_probs:
        max_prob = max(precip_probs)
        if max_prob >= 70:
            score += 15
            drivers.append(f"High precipitation probability forecast ({max_prob}%)")

    if not drivers:
        drivers.append("No significant severe weather risk factors detected in available data.")

    return min(score, 100), drivers, list(set(based_on))


# --------------------------------------------------------------------------
# Summary text builders
# --------------------------------------------------------------------------

def _wildfire_summary(risk: str, score: int) -> str:
    base = f"Wildfire spread risk is {risk} (heuristic score {score}/100)."
    if risk == "high":
        return (
            f"{base} Conditions are highly favorable for fire spread. "
            "Avoid outdoor burning and monitor fire agency alerts closely."
        )
    if risk == "medium":
        return (
            f"{base} Some conditions are conducive to fire spread. "
            "Stay alert to local fire agency updates."
        )
    return f"{base} Current conditions do not suggest elevated spread risk."


def _flood_summary(risk: str, score: int) -> str:
    base = f"Flood risk is {risk} (heuristic score {score}/100)."
    if risk == "high":
        return (
            f"{base} Active flood alerts and forecast precipitation indicate "
            "significant flood potential."
        )
    if risk == "medium":
        return (
            f"{base} Elevated precipitation or active weather alerts suggest "
            "increased flood awareness is warranted."
        )
    return f"{base} No significant flood indicators found for this location."


def _severe_weather_summary(risk: str, score: int) -> str:
    base = f"Severe weather risk is {risk} (heuristic score {score}/100)."
    if risk == "high":
        return (
            f"{base} Active severe alerts and adverse forecast conditions "
            "suggest significant severe weather potential."
        )
    if risk == "medium":
        return (
            f"{base} Some elevated wind or precipitation forecast alongside "
            "regional alerts warrant caution."
        )
    return f"{base} No significant severe weather indicators found for this location."


# --------------------------------------------------------------------------
# Public prediction functions
# --------------------------------------------------------------------------

async def predict_wildfire_spread(
    lat: float, lon: float, hours: int = 24
) -> HazardPrediction:
    """Generate a heuristic wildfire spread risk prediction for a location."""
    async with httpx.AsyncClient(timeout=20) as client:
        hourly_data, all_signals = await asyncio.gather(
            open_meteo.fetch_hourly_forecast(client, lat, lon, forecast_days=2),
            fetch_all_signals(),
        )

    nearby = filter_signals_near(all_signals, lat, lon, radius_km=WILDFIRE_RADIUS_KM)
    score, drivers, based_on = _score_wildfire(nearby, hourly_data)
    risk = _score_to_risk(score)

    return HazardPrediction(
        hazard_type="wildfire-spread",
        latitude=lat,
        longitude=lon,
        valid_from=utcnow_iso(),
        valid_to=hours_from_now_iso(hours),
        risk_level=risk,
        confidence=_score_to_confidence(len(drivers)),
        score=score,
        drivers=drivers,
        based_on=based_on,
        summary=_wildfire_summary(risk, score),
    )


async def predict_flood_risk(
    lat: float, lon: float, hours: int = 72
) -> HazardPrediction:
    """Generate a heuristic flood risk prediction for a location."""
    async with httpx.AsyncClient(timeout=20) as client:
        hourly_data, all_signals = await asyncio.gather(
            open_meteo.fetch_hourly_forecast(client, lat, lon, forecast_days=3),
            fetch_all_signals(),
        )

    nearby = filter_signals_near(all_signals, lat, lon, radius_km=FLOOD_RADIUS_KM)
    score, drivers, based_on = _score_flood(nearby, hourly_data)
    risk = _score_to_risk(score)

    return HazardPrediction(
        hazard_type="flood-risk",
        latitude=lat,
        longitude=lon,
        valid_from=utcnow_iso(),
        valid_to=hours_from_now_iso(hours),
        risk_level=risk,
        confidence=_score_to_confidence(len(drivers)),
        score=score,
        drivers=drivers,
        based_on=based_on,
        summary=_flood_summary(risk, score),
    )


async def predict_severe_weather_risk(
    lat: float, lon: float, hours: int = 24
) -> HazardPrediction:
    """Generate a heuristic severe weather risk prediction for a location."""
    async with httpx.AsyncClient(timeout=20) as client:
        hourly_data, all_signals = await asyncio.gather(
            open_meteo.fetch_hourly_forecast(client, lat, lon, forecast_days=2),
            fetch_all_signals(),
        )

    nearby = filter_signals_near(all_signals, lat, lon, radius_km=SEVERE_WEATHER_RADIUS_KM)
    score, drivers, based_on = _score_severe_weather(nearby, hourly_data)
    risk = _score_to_risk(score)

    return HazardPrediction(
        hazard_type="severe-weather-risk",
        latitude=lat,
        longitude=lon,
        valid_from=utcnow_iso(),
        valid_to=hours_from_now_iso(hours),
        risk_level=risk,
        confidence=_score_to_confidence(len(drivers)),
        score=score,
        drivers=drivers,
        based_on=based_on,
        summary=_severe_weather_summary(risk, score),
    )


async def get_prediction_summary(lat: float, lon: float) -> PredictionSummary:
    """Return a combined risk summary for all hazard types at a location.

    Runs all three hazard predictions in parallel for performance.
    """
    wildfire, flood, severe = await asyncio.gather(
        predict_wildfire_spread(lat, lon),
        predict_flood_risk(lat, lon),
        predict_severe_weather_risk(lat, lon),
    )
    return PredictionSummary(
        latitude=lat,
        longitude=lon,
        generated_at=utcnow_iso(),
        wildfire_spread=wildfire,
        flood_risk=flood,
        severe_weather_risk=severe,
    )
