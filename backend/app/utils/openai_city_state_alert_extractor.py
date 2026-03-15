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

ALERT_CATEGORY_OPTIONS = [
    "hazard update",
    "advisory",
    "closure",
    "evacuation",
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


def _impact_type_label(impact_type: str) -> str:
    labels = {
        "flooding": "Flooding",
        "road_closure": "Road Closure",
        "debris": "Debris",
        "structure_damage": "Structural Damage",
        "high_wind": "High Wind",
        "rain": "Heavy Rain",
        "powerline_failure": "Power Line Failure",
    }
    return labels.get(impact_type, impact_type.replace("_", " ").title())


def _build_city_state_snapshot(raw_step: dict[str, Any]) -> dict[str, Any]:
    """Pre-process raw city state data into a concise, LLM-friendly snapshot."""
    city_state = raw_step.get("city_state", {}) or {}
    affected_areas: list[dict[str, Any]] = city_state.get("affected_areas", []) or []
    impact_summary = city_state.get("impact_summary", {}) or {}
    overall = int(city_state.get("overall_severity", 0))

    # Group by impact type and find notable events
    by_type: dict[str, list[dict[str, Any]]] = {}
    for area in affected_areas:
        itype = str(area.get("impact_type", "unknown"))
        if itype in ("rain",):
            continue  # Skip raw rain points — too many, not alert-worthy
        by_type.setdefault(itype, []).append(area)

    type_summaries: list[dict[str, Any]] = []
    for itype, areas in by_type.items():
        severities = [int(a.get("severity", 0)) for a in areas]
        statuses = [str(a.get("status", "unknown")) for a in areas]
        worsening_count = sum(1 for s in statuses if s == "worsening")
        new_count = sum(1 for s in statuses if s == "new")

        # Pick the top 3 most severe locations for this type
        sorted_areas = sorted(areas, key=lambda a: int(a.get("severity", 0)), reverse=True)
        top_locations = [
            {
                "lat": round(float(a.get("lat", 0)), 4),
                "lon": round(float(a.get("lon", 0)), 4),
                "severity": int(a.get("severity", 0)),
                "status": str(a.get("status", "unknown")),
                "danger": str(a.get("danger_to_remain", "unknown")),
            }
            for a in sorted_areas[:3]
        ]

        type_summaries.append({
            "impact_type": _impact_type_label(itype),
            "impact_type_raw": itype,
            "count": len(areas),
            "max_severity": max(severities) if severities else 0,
            "avg_severity": round(sum(severities) / len(severities)) if severities else 0,
            "worsening_count": worsening_count,
            "new_count": new_count,
            "top_locations": top_locations,
        })

    # Sort by max severity descending so most important types come first
    type_summaries.sort(key=lambda t: t["max_severity"], reverse=True)

    return {
        "step_time": str(raw_step.get("time", "")),
        "overall_severity": overall,
        "danger_to_remain": str(city_state.get("danger_to_remain", "unknown")),
        "operational_status": str(city_state.get("operational_status", "unknown")),
        "recommended_action": str(city_state.get("recommended_action", "")),
        "total_affected_points": int(impact_summary.get("affected_points", 0)),
        "impact_breakdown": type_summaries,
        "city_services": city_state.get("city_services", {}),
    }


SYSTEM_PROMPT = """You are a disaster alert writer for a crisis management app in Vilankulo, Mozambique during a severe tropical cyclone. You receive a structured snapshot of city conditions and must generate specific, actionable alerts.

RULES:
- Each alert must describe a SPECIFIC event with real detail (not generic summaries)
- Reference actual coordinates, impact types, and severity levels from the data
- Write in clear, direct English suitable for emergency communication
- Area field should be a human-readable location description (e.g. "EN1 South of Vilankulo", "Bairro 3 Waterfront")
- Status must reflect the current trend: "Developing", "Intensifying", "Worsening", "Active", "Critical", "Easing", "Persisting", or "Guidance"
- For advisory category alerts, provide practical safety guidance (water safety, shelter tips, radio frequencies, etc.)

Return strict JSON with this shape:
{
  "cards": [{"headline": "...", "details": "...", "severity": "low|medium|high|extreme"}],
  "alerts": [
    {
      "title": "Short specific event headline",
      "details": "2-3 sentences with specific actionable information about this event",
      "urgency": "notification|caution|warning|urgent warning|alert|urgent alert|extreme urgency alert",
      "category": "hazard update|advisory|closure|evacuation",
      "area": "Human-readable location name",
      "status": "Developing|Intensifying|Worsening|Active|Critical|Easing|Persisting|Guidance",
      "lat": 0.0,
      "lon": 0.0
    }
  ]
}

Generate 2-3 cards and 3-6 alerts. At least one alert should be an advisory with practical guidance. Each alert should cover a different specific event or area. Prioritize the most severe and worsening conditions."""


def _fallback_city_state_output(raw_step: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Generate structured alerts without LLM, based directly on the affected areas data."""
    snapshot = _build_city_state_snapshot(raw_step)
    overall = snapshot["overall_severity"]
    breakdown = snapshot.get("impact_breakdown", [])

    cards: list[dict[str, Any]] = [
        {
            "headline": "City Operations",
            "details": (
                f"Status: {snapshot.get('operational_status', 'unknown').replace('_', ' ')}. "
                f"Danger to remain: {snapshot.get('danger_to_remain', 'unknown')}. "
                f"{snapshot.get('recommended_action', '')}"
            ),
            "severity": _severity_from_overall(overall),
        },
    ]

    if breakdown:
        top = breakdown[0]
        cards.append({
            "headline": f"{top['impact_type']} — Primary Concern",
            "details": (
                f"{top['count']} affected points, peak severity {top['max_severity']}/100. "
                f"{top['worsening_count']} worsening, {top['new_count']} newly detected."
            ),
            "severity": _severity_from_overall(top["max_severity"]),
        })

    if len(breakdown) > 1:
        secondary = breakdown[1]
        cards.append({
            "headline": f"{secondary['impact_type']} — Secondary Impact",
            "details": (
                f"{secondary['count']} points detected, peak severity {secondary['max_severity']}/100."
            ),
            "severity": _severity_from_overall(secondary["max_severity"]),
        })

    # Generate one alert per impact type (up to 5), plus an advisory
    alerts: list[dict[str, Any]] = []
    for entry in breakdown[:5]:
        if not entry["top_locations"]:
            continue
        top_loc = entry["top_locations"][0]
        status_val = "Worsening" if entry["worsening_count"] > 0 else ("Active" if entry["new_count"] == 0 else "Developing")
        alerts.append({
            "title": f"{entry['impact_type']} reported near ({top_loc['lat']:.3f}, {top_loc['lon']:.3f})",
            "details": (
                f"{entry['count']} {entry['impact_type'].lower()} points detected. "
                f"Peak severity {entry['max_severity']}/100 with {entry['worsening_count']} worsening. "
                f"Danger level: {top_loc['danger']}."
            ),
            "urgency": _urgency_from_overall(entry["max_severity"]),
            "category": "closure" if entry["impact_type_raw"] == "road_closure" else "hazard update",
            "area": f"Vilankulo ({top_loc['lat']:.3f}, {top_loc['lon']:.3f})",
            "status": status_val,
            "lat": top_loc["lat"],
            "lon": top_loc["lon"],
        })

    # Always include an advisory
    alerts.append({
        "title": "Monitor emergency communications",
        "details": (
            f"Overall city severity is {overall}/100. "
            f"Tune to Radio Mozambique 97.9 FM for official updates. "
            f"Conserve phone battery and avoid unnecessary travel."
        ),
        "urgency": "notification",
        "category": "advisory",
        "area": "Vilankulo Municipality",
        "status": "Guidance",
        "lat": None,
        "lon": None,
    })

    return {"cards": cards[:3], "alerts": alerts[:6]}


async def extract_city_state_alerts_and_cards(
    raw_step: dict[str, Any],
    use_llm: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    if not use_llm or not settings.openai_api_key:
        return _fallback_city_state_output(raw_step)

    snapshot = _build_city_state_snapshot(raw_step)
    user_prompt = json.dumps(snapshot, ensure_ascii=False)

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
        cards_raw = parsed.get("cards", [])
        alerts_raw = parsed.get("alerts", [])

        cards: list[dict[str, Any]] = []
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

        alerts: list[dict[str, Any]] = []
        for alert in alerts_raw:
            if not isinstance(alert, dict):
                continue
            title = str(alert.get("title", "")).strip()
            details = str(alert.get("details", "")).strip()
            urgency = str(alert.get("urgency", "warning")).strip().lower()
            if urgency not in ALERT_URGENCY_OPTIONS:
                urgency = "warning"
            category = str(alert.get("category", "hazard update")).strip()
            if category not in ALERT_CATEGORY_OPTIONS:
                category = "hazard update"
            status = str(alert.get("status", "Active")).strip()

            lat_val = alert.get("lat")
            lon_val = alert.get("lon")
            lat = float(lat_val) if lat_val is not None else None
            lon = float(lon_val) if lon_val is not None else None

            if title and details:
                alerts.append({
                    "title": title,
                    "details": details,
                    "urgency": urgency,
                    "category": category,
                    "area": str(alert.get("area", "Vilankulo")),
                    "status": status,
                    "lat": lat,
                    "lon": lon,
                })

        if cards and alerts:
            return {"cards": cards[:3], "alerts": alerts[:6]}
    except Exception:
        return _fallback_city_state_output(raw_step)

    return _fallback_city_state_output(raw_step)
