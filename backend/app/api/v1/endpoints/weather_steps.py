from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.weather_step_models import WeatherStepResponse
from app.services import weather_steps_service

router = APIRouter(prefix="/information/weather", tags=["information-weather"])


@router.get("/current-step", response_model=WeatherStepResponse)
async def get_weather_current_step(
    step: int = Query(..., ge=0, description="0-based weather step index"),
    beautify: bool = Query(True, description="When false, skip OpenAI beautification"),
) -> WeatherStepResponse:
    try:
        return await weather_steps_service.get_weather_current_step(step, beautify=beautify)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/next-step", response_model=WeatherStepResponse)
async def get_weather_next_step(
    curr_step: int = Query(..., ge=0, description="0-based current weather step index"),
    beautify: bool = Query(True, description="When false, skip OpenAI beautification"),
) -> WeatherStepResponse:
    return await weather_steps_service.get_weather_next_step(curr_step, beautify=beautify)
