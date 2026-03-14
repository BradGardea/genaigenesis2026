from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


def _fallback_cards(raw_step: dict[str, Any]) -> list[dict[str, str]]:
    weather = raw_step.get("weather", {}) if isinstance(raw_step.get("weather"), dict) else {}
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
    evac = (
        raw_step.get("evacuation_signal", {})
        if isinstance(raw_step.get("evacuation_signal"), dict)
        else {}
    )

    severe_level = str(severe.get("risk_level", "medium")).lower()
    severity_map = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "extreme": "extreme",
    }
    severity = severity_map.get(severe_level, "medium")

    return [
        {
            "headline": "Storm Update",
            "details": (
                f"Wind {weather.get('wind_speed_kmh', 'n/a')} km/h, rain {weather.get('rainfall_mm_10min', 'n/a')} mm/10min, "
                f"visibility {weather.get('visibility_km', 'n/a')} km."
            ),
            "severity": severity,
        },
        {
            "headline": "Risk Summary",
            "details": (
                f"Flood risk: {flood.get('risk_level', 'n/a')} (score {flood.get('score', 'n/a')}). "
                f"Severe weather risk: {severe.get('risk_level', 'n/a')} (score {severe.get('score', 'n/a')})."
            ),
            "severity": severity,
        },
        {
            "headline": "Evacuation Signal",
            "details": (
                f"Status: {evac.get('status', 'monitor')}. "
                f"{evac.get('recommended_action', 'Continue monitoring official guidance.')}"
            ),
            "severity": "medium" if str(evac.get("status", "monitor")).lower() == "monitor" else "high",
        },
    ]


async def beautify_weather_step(raw_step: dict[str, Any]) -> list[dict[str, str]]:
    """Return human-friendly weather cards; uses OpenAI when configured."""
    if not settings.openai_api_key:
        return _fallback_cards(raw_step)

    system_prompt = (
        "You transform raw weather hazard timestep JSON into concise user-facing weather cards. "
        "Return strict JSON only with shape: "
        '{"cards":[{"headline":"...","details":"...","severity":"low|medium|high|extreme"}]}. '
        "Create exactly 3 cards. Keep each details <= 180 characters."
    )

    user_prompt = json.dumps({"raw_step": raw_step}, ensure_ascii=False)

    payload = {
        "model": settings.openai_weather_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
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
            if severity not in {"low", "medium", "high", "extreme"}:
                severity = "medium"
            if headline and details:
                normalized.append(
                    {"headline": headline, "details": details, "severity": severity}
                )
        if normalized:
            return normalized[:3]
    except Exception:
        return _fallback_cards(raw_step)

    return _fallback_cards(raw_step)
