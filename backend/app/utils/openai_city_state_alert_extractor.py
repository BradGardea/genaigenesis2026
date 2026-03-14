from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
ALERT_URGENCY_OPTIONS = [
    "notification",
    "caution",
    "warning",
    "urgent warning",
    "alert",
    "urgent alert",
    "extreme urgency alert",
]


def _severity_from_overall(overall: int) -> str:
    if overall >= 85:
        return "extreme"
    if overall >= 65:
        return "high"
    if overall >= 35:
        return "medium"
    return "low"


def _urgency_from_overall(overall: int) -> str:
    if overall >= 90:
        return "extreme urgency alert"
    if overall >= 75:
        return "urgent alert"
    if overall >= 60:
        return "alert"
    if overall >= 45:
        return "urgent warning"
    if overall >= 30:
        return "warning"
    if overall >= 15:
        return "caution"
    return "notification"


def _fallback_city_state_output(raw_step: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    city_state = (
        raw_step.get("city_state", {}) if isinstance(raw_step.get("city_state"), dict) else {}
    )
    impact_summary = (
        city_state.get("impact_summary", {})
        if isinstance(city_state.get("impact_summary"), dict)
        else {}
    )
    overall = int(city_state.get("overall_severity", 0))
    dominant = city_state.get("dominant_impacts", [])
    dominant_str = ", ".join(str(item) for item in dominant) if dominant else "mixed impacts"

    cards = [
        {
            "headline": "City Operations",
            "details": (
                f"Status: {city_state.get('operational_status', 'unknown')}. "
                f"Danger to remain: {city_state.get('danger_to_remain', 'unknown')}."
            ),
            "severity": _severity_from_overall(overall),
        },
        {
            "headline": "Dominant Impacts",
            "details": (
                f"{dominant_str}. Affected points: {impact_summary.get('affected_points', 0)}. "
                f"Flood points: {impact_summary.get('flooding_points', 0)}."
            ),
            "severity": _severity_from_overall(overall),
        },
        {
            "headline": "Recommended Action",
            "details": str(city_state.get("recommended_action", "Monitor official updates.")),
            "severity": "medium",
        },
    ]

    alerts = [
        {
            "title": f"City Impact Update ({city_state.get('operational_status', 'status change')})",
            "details": (
                f"Overall severity {overall}/100 with {impact_summary.get('affected_points', 0)} affected points. "
                f"Primary impacts: {dominant_str}."
            ),
            "urgency": _urgency_from_overall(overall),
            "category": "hazard update",
            "area": str(city_state.get("danger_to_remain", "city-wide")).replace("_", " ").title(),
            "source": "City Impact Model",
        }
    ]

    return {"cards": cards, "alerts": alerts}


async def extract_city_state_alerts_and_cards(
    raw_step: dict[str, Any],
) -> dict[str, list[dict[str, str]]]:
    if not settings.openai_api_key:
        return _fallback_city_state_output(raw_step)

    system_prompt = (
        "You transform city-state disaster timestep JSON into card summaries and alert records. "
        "Return strict JSON only with shape: "
        '{"cards":[{"headline":"...","details":"...","severity":"low|medium|high|extreme"}],'
        '"alerts":[{"title":"...","details":"...","urgency":"...","category":"...","area":"...","source":"..."}]}. '
        f"Alert urgency must be one of: {', '.join(ALERT_URGENCY_OPTIONS)}. "
        "Create exactly 3 cards and 1-3 alerts."
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
        cards_raw = parsed.get("cards", [])
        alerts_raw = parsed.get("alerts", [])

        cards: list[dict[str, str]] = []
        for card in cards_raw:
            if not isinstance(card, dict):
                continue
            headline = str(card.get("headline", "")).strip()
            details = str(card.get("details", "")).strip()
            severity = str(card.get("severity", "medium")).strip().lower()
            if severity not in {"low", "medium", "high", "extreme"}:
                severity = "medium"
            if headline and details:
                cards.append(
                    {"headline": headline, "details": details, "severity": severity}
                )

        alerts: list[dict[str, str]] = []
        for alert in alerts_raw:
            if not isinstance(alert, dict):
                continue
            title = str(alert.get("title", "")).strip()
            details = str(alert.get("details", "")).strip()
            urgency = str(alert.get("urgency", "warning")).strip().lower()
            if urgency not in ALERT_URGENCY_OPTIONS:
                urgency = "warning"
            if title and details:
                alerts.append(
                    {
                        "title": title,
                        "details": details,
                        "urgency": urgency,
                        "category": str(alert.get("category", "hazard update")),
                        "area": str(alert.get("area", "City Wide")),
                        "source": str(alert.get("source", "City Impact Model")),
                    }
                )

        if cards and alerts:
            return {"cards": cards[:3], "alerts": alerts[:3]}
    except Exception:
        return _fallback_city_state_output(raw_step)

    return _fallback_city_state_output(raw_step)
