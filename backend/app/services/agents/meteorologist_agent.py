"""Meteorologist agent — analyzes weather/storm data and produces a briefing."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from app.providers.base_agent import BaseAgent
from app.schemas.agent_models import (
    AgentBriefingRequest,
    AgentBriefingResponse,
    MeteorologistOutput,
)
from app.services import alerts_service, forecasts_service, storms_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert meteorologist analyzing crisis conditions for emergency planners.
Given alerts, forecast data, and active storms, produce a concise situational briefing.

You must respond with ONLY a JSON object — no markdown, no extra text.

Response schema:
{
  "summary": "<2-3 sentence overview>",
  "risk_level": "<low|medium|high|extreme>",
  "active_alerts_count": <int>,
  "key_threats": ["<threat1>", ...],
  "forecast_outlook": "<1-2 sentences>",
  "recommended_actions": ["<action1>", ...]
}
"""


class MeteorologistAgent(BaseAgent[MeteorologistOutput]):
    agent_name = "meteorologist"
    system_prompt = SYSTEM_PROMPT
    max_tokens = 600

    def build_user_prompt(self, context: dict) -> str:
        parts: list[str] = []
        lat = context.get("latitude")
        lon = context.get("longitude")
        if lat is not None and lon is not None:
            parts.append(f"Location: ({lat:.4f}, {lon:.4f})")

        alerts = context.get("alerts", [])
        if alerts:
            parts.append(f"Active alerts ({len(alerts)}):")
            for a in alerts[:10]:
                title = getattr(a, "title", None) or getattr(a, "headline", str(a))
                parts.append(f"  - {title}")
        else:
            parts.append("No active alerts.")

        forecast = context.get("forecast")
        if forecast:
            hours = getattr(forecast, "hours", None) or []
            if hours:
                temps = [h.temperature_c for h in hours[:12] if h.temperature_c is not None]
                winds = [h.wind_speed_kmh for h in hours[:12] if h.wind_speed_kmh is not None]
                precips = [h.precipitation_probability for h in hours[:12] if h.precipitation_probability is not None]
                if temps:
                    parts.append(f"Next 12h temps: {min(temps):.0f}–{max(temps):.0f}°C")
                if winds:
                    parts.append(f"Next 12h winds: up to {max(winds):.0f} km/h")
                if precips:
                    parts.append(f"Next 12h precip probability: up to {max(precips):.0f}%")

        storms = context.get("storms", [])
        if storms:
            parts.append(f"Active tropical storms ({len(storms)}):")
            for s in storms[:5]:
                name = getattr(s, "name", str(s))
                parts.append(f"  - {name}")

        return "\n".join(parts)

    def parse_response(self, raw_text: str) -> MeteorologistOutput | None:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
            return MeteorologistOutput(**data)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    def fallback(self, context: dict) -> MeteorologistOutput:
        alerts = context.get("alerts", [])
        storms = context.get("storms", [])
        forecast = context.get("forecast")

        alert_count = len(alerts)
        storm_count = len(storms)

        # Determine risk level heuristically
        if alert_count >= 5 or storm_count >= 2:
            risk = "high"
        elif alert_count >= 2 or storm_count >= 1:
            risk = "medium"
        else:
            risk = "low"

        key_threats: list[str] = []
        if storm_count:
            key_threats.append(f"{storm_count} active tropical storm(s)")
        if alert_count:
            key_threats.append(f"{alert_count} weather alert(s) in area")

        # Check forecast extremes
        outlook = "No significant weather expected."
        if forecast:
            hours = getattr(forecast, "hours", None) or []
            winds = [h.wind_speed_kmh for h in hours[:24] if h.wind_speed_kmh is not None]
            precips = [h.precipitation_probability for h in hours[:24] if h.precipitation_probability is not None]
            if winds and max(winds) > 80:
                key_threats.append("High winds forecast")
                risk = "high"
            if precips and max(precips) > 80:
                key_threats.append("Heavy precipitation likely")
                if risk == "low":
                    risk = "medium"
            if winds or precips:
                outlook = f"Winds up to {max(winds):.0f} km/h, precip chance up to {max(precips):.0f}% in next 24h." if winds and precips else "See forecast details."

        actions: list[str] = []
        if risk in ("high", "extreme"):
            actions.append("Monitor official advisories closely")
            actions.append("Prepare for possible evacuation")
        elif risk == "medium":
            actions.append("Stay weather-aware")
        else:
            actions.append("No immediate action required")

        return MeteorologistOutput(
            summary=f"{'Elevated' if risk != 'low' else 'Stable'} conditions with {alert_count} alert(s) and {storm_count} active storm(s).",
            risk_level=risk,
            active_alerts_count=alert_count,
            key_threats=key_threats,
            forecast_outlook=outlook,
            recommended_actions=actions,
        )


async def generate_meteorologist_briefing(
    request: AgentBriefingRequest,
) -> AgentBriefingResponse:
    """Service function: gather data, run agent, wrap response."""
    lat = request.latitude or 29.76
    lon = request.longitude or -95.37

    # Fetch context in parallel
    alerts_task = asyncio.create_task(alerts_service.fetch_all_signals())
    forecast_task = asyncio.create_task(forecasts_service.get_hourly_forecast(lat, lon))
    storms_task = asyncio.create_task(storms_service.get_active_storms())

    alerts, forecast, storms_resp = await asyncio.gather(
        alerts_task, forecast_task, storms_task, return_exceptions=True
    )

    # Gracefully handle failures
    if isinstance(alerts, BaseException):
        logger.warning("Failed to fetch alerts: %s", alerts)
        alerts = []
    if isinstance(forecast, BaseException):
        logger.warning("Failed to fetch forecast: %s", forecast)
        forecast = None
    if isinstance(storms_resp, BaseException):
        logger.warning("Failed to fetch storms: %s", storms_resp)
        storms_resp = None

    storms_list = getattr(storms_resp, "storms", []) if storms_resp else []

    context = {
        "latitude": lat,
        "longitude": lon,
        "alerts": alerts,
        "forecast": forecast,
        "storms": storms_list,
    }

    agent = MeteorologistAgent()
    output = await agent.run(context)

    # Determine status
    from app.core.config import settings
    import app.providers.watsonx_client as _mod

    if not settings.watsonx_api_key or _mod._watsonx_disabled:
        status = "fallback"
    else:
        status = "ok"

    return AgentBriefingResponse(
        agent_type="meteorologist",
        status=status,
        briefing=output.summary,
        structured_data=output.model_dump(),
        data_sources=["noaa-nws", "open-meteo", "nhc", "usgs", "nasa-firms", "gdacs"],
        generated_at=datetime.utcnow(),
    )
