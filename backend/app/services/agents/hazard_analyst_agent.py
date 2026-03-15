"""Hazard analyst agent — assesses multi-hazard risk conditions."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from app.providers.base_agent import BaseAgent
from app.schemas.agent_models import (
    AgentBriefingRequest,
    AgentBriefingResponse,
    HazardAnalystOutput,
)
from app.services import alerts_service, predictions_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a hazard risk analyst assessing multi-hazard conditions for emergency management.
Given prediction scores, active hazard zones, and alerts, produce a risk assessment.

You must respond with ONLY a JSON object — no markdown, no extra text.

Response schema:
{
  "summary": "<2-3 sentence risk overview>",
  "wildfire_risk": "<low|medium|high>",
  "flood_risk": "<low|medium|high>",
  "severe_weather_risk": "<low|medium|high>",
  "active_hazard_zones": <int>,
  "evacuation_recommended": <true|false>,
  "reasoning": "<why you recommend or don't recommend evacuation>"
}
"""


class HazardAnalystAgent(BaseAgent[HazardAnalystOutput]):
    agent_name = "hazard_analyst"
    system_prompt = SYSTEM_PROMPT
    max_tokens = 600

    def build_user_prompt(self, context: dict) -> str:
        parts: list[str] = []
        lat = context.get("latitude")
        lon = context.get("longitude")
        if lat is not None and lon is not None:
            parts.append(f"Location: ({lat:.4f}, {lon:.4f})")

        prediction_summary = context.get("prediction_summary")
        if prediction_summary:
            preds = getattr(prediction_summary, "predictions", {})
            if isinstance(preds, dict):
                for hazard_type, pred in preds.items():
                    score = getattr(pred, "score", None)
                    level = getattr(pred, "risk_level", None)
                    drivers = getattr(pred, "drivers", [])
                    parts.append(f"{hazard_type}: score={score}, level={level}, drivers={drivers}")
            else:
                parts.append(f"Predictions: {prediction_summary}")

        alerts = context.get("alerts", [])
        if alerts:
            parts.append(f"Active alerts ({len(alerts)}):")
            for a in alerts[:10]:
                title = getattr(a, "title", None) or getattr(a, "headline", str(a))
                source = getattr(a, "source", "unknown")
                parts.append(f"  - [{source}] {title}")
        else:
            parts.append("No active alerts.")

        hazard_zones = context.get("active_hazard_zones", 0)
        parts.append(f"Active hazard zones in system: {hazard_zones}")

        return "\n".join(parts)

    def parse_response(self, raw_text: str) -> HazardAnalystOutput | None:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
            return HazardAnalystOutput(**data)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    def fallback(self, context: dict) -> HazardAnalystOutput:
        prediction_summary = context.get("prediction_summary")
        alerts = context.get("alerts", [])
        hazard_zones = context.get("active_hazard_zones", 0)

        wildfire_risk = "low"
        flood_risk = "low"
        severe_weather_risk = "low"

        if prediction_summary:
            preds = getattr(prediction_summary, "predictions", {})
            if isinstance(preds, dict):
                for hazard_type, pred in preds.items():
                    level = getattr(pred, "risk_level", "low")
                    if "wildfire" in hazard_type:
                        wildfire_risk = level
                    elif "flood" in hazard_type:
                        flood_risk = level
                    elif "severe_weather" in hazard_type:
                        severe_weather_risk = level

        high_risks = [r for r in [wildfire_risk, flood_risk, severe_weather_risk] if r == "high"]
        evac = len(high_risks) >= 1 or hazard_zones >= 2

        if high_risks:
            summary = f"Elevated risk: {len(high_risks)} hazard type(s) at HIGH level with {len(alerts)} active alert(s)."
        elif any(r == "medium" for r in [wildfire_risk, flood_risk, severe_weather_risk]):
            summary = f"Moderate risk conditions with {len(alerts)} alert(s) and {hazard_zones} active zone(s)."
        else:
            summary = f"Low risk conditions. {len(alerts)} alert(s) being monitored."

        reasoning = (
            "Evacuation recommended due to high hazard levels."
            if evac
            else "Current conditions do not warrant evacuation."
        )

        return HazardAnalystOutput(
            summary=summary,
            wildfire_risk=wildfire_risk,
            flood_risk=flood_risk,
            severe_weather_risk=severe_weather_risk,
            active_hazard_zones=hazard_zones,
            evacuation_recommended=evac,
            reasoning=reasoning,
        )


async def generate_hazard_briefing(
    request: AgentBriefingRequest,
) -> AgentBriefingResponse:
    """Service function: gather data, run agent, wrap response."""
    lat = request.latitude or 29.76
    lon = request.longitude or -95.37

    # Fetch context in parallel
    alerts_task = asyncio.create_task(alerts_service.fetch_all_signals())
    predictions_task = asyncio.create_task(predictions_service.get_prediction_summary(lat, lon))

    alerts, prediction_summary = await asyncio.gather(
        alerts_task, predictions_task, return_exceptions=True
    )

    if isinstance(alerts, BaseException):
        logger.warning("Failed to fetch alerts: %s", alerts)
        alerts = []
    if isinstance(prediction_summary, BaseException):
        logger.warning("Failed to fetch predictions: %s", prediction_summary)
        prediction_summary = None

    # Count active hazard zones from the hazard store
    try:
        from app.services.hazard_store import store
        hazard_zones = len(store.get_hazards())
    except Exception:
        hazard_zones = 0

    context = {
        "latitude": lat,
        "longitude": lon,
        "alerts": alerts,
        "prediction_summary": prediction_summary,
        "active_hazard_zones": hazard_zones,
    }

    agent = HazardAnalystAgent()
    output = await agent.run(context)

    from app.core.config import settings
    import app.providers.watsonx_client as _mod

    if not settings.watsonx_api_key or _mod._watsonx_disabled:
        status = "fallback"
    else:
        status = "ok"

    return AgentBriefingResponse(
        agent_type="hazard_analyst",
        status=status,
        briefing=output.summary,
        structured_data=output.model_dump(),
        data_sources=["noaa-nws", "usgs", "nasa-firms", "gdacs", "open-meteo"],
        generated_at=datetime.utcnow(),
    )
