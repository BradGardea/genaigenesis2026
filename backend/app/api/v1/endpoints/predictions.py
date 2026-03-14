"""Prediction endpoints — heuristic hazard risk assessments.

All predictions are transparency-first heuristic estimates that combine
live disaster signals with weather forecast drivers. They are NOT
certified scientific forecasts. Always defer to official warnings.
"""

from fastapi import APIRouter, Query

from app.schemas.prediction_models import HazardPrediction, PredictionSummary
from app.services import predictions_service

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/summary", response_model=PredictionSummary)
async def prediction_summary(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
) -> PredictionSummary:
    """Combined hazard risk summary for a location.

    Runs wildfire spread, flood, and severe weather predictions in parallel
    and returns all three in a single response object.
    """
    return await predictions_service.get_prediction_summary(lat, lon)


@router.get("/wildfire-spread", response_model=HazardPrediction)
async def wildfire_spread_prediction(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    hours: int = Query(
        default=24, ge=1, le=120, description="Prediction window in hours"
    ),
) -> HazardPrediction:
    """Wildfire spread risk prediction.

    Combines nearby fire detections (NASA FIRMS) with forecast wind speed,
    temperature, and relative humidity (Open-Meteo) to produce a heuristic
    risk score and plain-language explanation.
    """
    return await predictions_service.predict_wildfire_spread(lat, lon, hours)


@router.get("/flood-risk", response_model=HazardPrediction)
async def flood_risk_prediction(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    hours: int = Query(
        default=72, ge=1, le=168, description="Prediction window in hours"
    ),
) -> HazardPrediction:
    """Flood risk prediction.

    Combines active flood-related alerts (NOAA NWS, GDACS) with forecast
    precipitation probability (Open-Meteo) to produce a heuristic risk score.
    """
    return await predictions_service.predict_flood_risk(lat, lon, hours)


@router.get("/severe-weather-risk", response_model=HazardPrediction)
async def severe_weather_risk_prediction(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    hours: int = Query(
        default=24, ge=1, le=120, description="Prediction window in hours"
    ),
) -> HazardPrediction:
    """Severe weather risk prediction.

    Combines active severe/extreme alerts (NOAA NWS) with forecast wind
    speed and precipitation probability (Open-Meteo).
    """
    return await predictions_service.predict_severe_weather_risk(lat, lon, hours)
