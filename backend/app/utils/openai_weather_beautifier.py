from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

# Map of weather condition keywords to glyph identifiers the frontend can render
_CONDITION_KEYWORDS: list[tuple[str, str]] = [
    ("tornado", "tornado"),
    ("cyclone", "cyclone"),
    ("typhoon", "cyclone"),
    ("hurricane", "cyclone"),
    ("thunder", "thunderstorm"),
    ("lightning", "thunderstorm"),
    ("storm surge", "storm_surge"),
    ("surge", "storm_surge"),
    ("flood", "flooding"),
    ("inundat", "flooding"),
    ("rain", "heavy_rain"),
    ("precip", "heavy_rain"),
    ("downpour", "heavy_rain"),
    ("wind", "high_wind"),
    ("gust", "high_wind"),
    ("gale", "high_wind"),
    ("visibility", "low_visibility"),
    ("fog", "low_visibility"),
    ("pressure", "pressure"),
    ("baro", "pressure"),
]


def _infer_condition(headline: str, details: str) -> str:
    """Infer a weather condition type from card text for glyph mapping."""
    combined = (headline + " " + details).lower()
    for keyword, condition in _CONDITION_KEYWORDS:
        if keyword in combined:
            return condition
    return "general"


def _build_weather_snapshot(raw_step: dict[str, Any]) -> dict[str, Any]:
    """Pre-process raw weather step into a focused snapshot for the LLM."""
    snapshot: dict[str, Any] = {}

    # Core weather conditions
    weather = raw_step.get("weather", {})
    if isinstance(weather, dict):
        snapshot["conditions"] = {
            "temperature_c": weather.get("temperature_c"),
            "wind_speed_kmh": weather.get("wind_speed_kmh"),
            "rainfall_mm_10min": weather.get("rainfall_mm_10min"),
            "visibility_km": weather.get("visibility_km"),
            "pressure_hpa": weather.get("pressure_hpa"),
            "humidity_pct": weather.get("relative_humidity"),
            "precipitation_probability": weather.get("precipitation_probability"),
        }

    # Storm state
    storm = raw_step.get("storm_state", {})
    if isinstance(storm, dict) and storm.get("storm_center"):
        center = storm["storm_center"]
        movement = storm.get("movement", {})
        radii = storm.get("wind_radii_km", {})
        snapshot["storm"] = {
            "type": storm.get("storm_type", "unknown"),
            "center_lat": center.get("lat"),
            "center_lon": center.get("lon"),
            "movement_direction_deg": movement.get("direction_deg") if isinstance(movement, dict) else None,
            "movement_speed_kmh": movement.get("speed_kmh") if isinstance(movement, dict) else None,
            "max_wind_radius_km": storm.get("radius_of_maximum_wind_km"),
            "wind_radii_km": {
                "34kt": radii.get("r34", 0),
                "50kt": radii.get("r50", 0),
                "64kt": radii.get("r64", 0),
            },
        }
        # Focus points (heaviest rain, strongest wind, etc.)
        focus = storm.get("focus_points", [])
        if isinstance(focus, list) and focus:
            snapshot["storm"]["focus_points"] = [
                {"name": fp.get("name", ""), "lat": fp.get("lat"), "lon": fp.get("lon")}
                for fp in focus[:5]
                if isinstance(fp, dict)
            ]
        # Near-term forecast
        forecast_next = storm.get("forecast_next", {})
        if isinstance(forecast_next, dict):
            fc_entries = []
            for period, fc_data in sorted(forecast_next.items()):
                if isinstance(fc_data, dict) and fc_data.get("storm_center"):
                    fc_entries.append({
                        "period": period,
                        "center_lat": fc_data["storm_center"].get("lat"),
                        "center_lon": fc_data["storm_center"].get("lon"),
                        "wind_speed_kmh": fc_data.get("weather", {}).get("wind_speed_kmh")
                        if isinstance(fc_data.get("weather"), dict) else None,
                    })
            if fc_entries:
                snapshot["storm"]["forecast_track"] = fc_entries

    # Risk predictions
    prediction = raw_step.get("prediction_summary", {})
    if isinstance(prediction, dict):
        risks: dict[str, Any] = {}
        for risk_key in ("flood_risk", "severe_weather_risk"):
            risk = prediction.get(risk_key, {})
            if isinstance(risk, dict) and risk.get("risk_level"):
                risks[risk_key] = {
                    "risk_level": risk.get("risk_level"),
                    "score": risk.get("score"),
                    "drivers": risk.get("drivers", []),
                    "summary": risk.get("summary", ""),
                }
        if risks:
            snapshot["risks"] = risks

    snapshot["time"] = str(raw_step.get("time", ""))

    return snapshot


SYSTEM_PROMPT = """\
You are a meteorological analyst writing weather briefing cards for CrisisNet, \
a disaster response app serving civilians in Vilankulo, Mozambique during a severe cyclone event.

Given a weather data snapshot, produce exactly 4 JSON cards. Each card must have:
- "headline": Short, punchy title (max 60 chars). Use specific numbers from the data.
- "details": 1-3 sentences of analysis (max 200 chars). Reference specific values, \
locations, trends. Be direct and actionable.
- "severity": One of "low", "medium", "high", "extreme".
- "conditionType": One of "cyclone", "thunderstorm", "heavy_rain", "high_wind", \
"flooding", "storm_surge", "low_visibility", "pressure", "tornado", "general".

The 4 cards MUST cover:
1. **Storm Position & Track** - Current storm center, movement, radius. Where is the cyclone \
heading? How fast? Use lat/lon and km values.
2. **Wind & Pressure** - Wind speeds, gusts, wind radii, barometric pressure. \
How dangerous are conditions right now?
3. **Rainfall & Flood Risk** - Precipitation rates, accumulations, flood risk score, \
visibility. What is the water threat?
4. **Risk Outlook** - Near-term forecast (30-90 min), trajectory changes, intensification \
or weakening trend. What should people prepare for next?

Do NOT include evacuation instructions or action recommendations. Focus purely on \
weather data interpretation and risk assessment.

Return strict JSON: {"cards": [...]}
"""


def _fallback_cards(raw_step: dict[str, Any]) -> list[dict[str, str]]:
    """Generate rule-based weather cards when LLM is unavailable."""
    weather = raw_step.get("weather", {}) if isinstance(raw_step.get("weather"), dict) else {}
    storm = raw_step.get("storm_state", {}) if isinstance(raw_step.get("storm_state"), dict) else {}
    prediction = (
        raw_step.get("prediction_summary", {})
        if isinstance(raw_step.get("prediction_summary"), dict)
        else {}
    )
    flood = prediction.get("flood_risk", {}) if isinstance(prediction.get("flood_risk"), dict) else {}
    severe = (
        prediction.get("severe_weather_risk", {})
        if isinstance(prediction.get("severe_weather_risk"), dict)
        else {}
    )

    severe_level = str(severe.get("risk_level", "medium")).lower()
    severity_map = {"low": "low", "medium": "medium", "high": "high", "extreme": "extreme"}
    severity = severity_map.get(severe_level, "medium")

    wind_speed = weather.get("wind_speed_kmh", "n/a")
    rainfall = weather.get("rainfall_mm_10min", "n/a")

    # Card 1: Storm position
    center = storm.get("storm_center", {})
    movement = storm.get("movement", {})
    card1_details = f"Storm centered near {center.get('lat', '?')}N, {center.get('lon', '?')}E"
    if isinstance(movement, dict) and movement.get("speed_kmh"):
        card1_details += f", moving at {movement['speed_kmh']} km/h"
    card1_details += "."

    # Card 2: Wind & pressure
    pressure = weather.get("pressure_hpa", "n/a")
    radii = storm.get("wind_radii_km", {})
    card2_details = f"Sustained winds {wind_speed} km/h, pressure {pressure} hPa."
    if isinstance(radii, dict) and radii.get("r64"):
        card2_details += f" Hurricane-force winds extend {radii['r64']} km from center."

    # Card 3: Rainfall & flood risk
    visibility = weather.get("visibility_km", "n/a")
    flood_level = flood.get("risk_level", "unknown")
    flood_score = flood.get("score", "n/a")
    card3_details = (
        f"Rainfall {rainfall} mm/10min, visibility {visibility} km. "
        f"Flood risk: {flood_level} (score {flood_score})."
    )

    # Card 4: Risk outlook
    severe_level_str = severe.get("risk_level", "unknown")
    severe_score = severe.get("score", "n/a")
    card4_details = (
        f"Severe weather risk: {severe_level_str} (score {severe_score}). "
        f"Conditions expected to intensify in the near term."
    )

    wind_sev = "extreme" if isinstance(wind_speed, (int, float)) and wind_speed > 120 else severity

    return [
        {
            "headline": "Disaster Position Update",
            "details": card1_details,
            "severity": severity,
            "conditionType": "cyclone",
        },
        {
            "headline": f"Wind & Pressure: {wind_speed} km/h",
            "details": card2_details,
            "severity": wind_sev,
            "conditionType": "high_wind",
        },
        {
            "headline": f"Rainfall & Flood Risk: {flood_level.title()}",
            "details": card3_details,
            "severity": severity,
            "conditionType": "heavy_rain" if flood_level in ("high", "extreme") else "flooding",
        },
        {
            "headline": "Risk Outlook",
            "details": card4_details,
            "severity": severity,
            "conditionType": "general",
        },
    ]


_VALID_CONDITIONS = {
    "cyclone", "thunderstorm", "heavy_rain", "high_wind", "flooding",
    "storm_surge", "low_visibility", "pressure", "tornado", "general",
}


async def beautify_weather_step(
    raw_step: dict[str, Any], use_llm: bool = True
) -> list[dict[str, str]]:
    """Return human-friendly weather cards; uses OpenAI when configured."""
    if not use_llm or not settings.openai_api_key:
        return _fallback_cards(raw_step)

    snapshot = _build_weather_snapshot(raw_step)
    user_prompt = json.dumps({"weather_snapshot": snapshot}, ensure_ascii=False)

    payload = {
        "model": settings.openai_weather_model,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OPENAI_CHAT_COMPLETIONS_URL, headers=headers, json=payload
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        cards = parsed.get("cards", [])
        normalized: list[dict[str, str]] = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            headline = str(card.get("headline", "")).strip()
            details = str(card.get("details", "")).strip()
            severity = str(card.get("severity", "medium")).strip().lower()
            condition_type = str(card.get("conditionType", "")).strip().lower()

            if severity not in {"low", "medium", "high", "extreme"}:
                severity = "medium"
            if condition_type not in _VALID_CONDITIONS:
                condition_type = _infer_condition(headline, details)

            if headline and details:
                normalized.append({
                    "headline": headline,
                    "details": details,
                    "severity": severity,
                    "conditionType": condition_type,
                })
        if normalized:
            return normalized[:4]
    except Exception:
        return _fallback_cards(raw_step)

    return _fallback_cards(raw_step)
