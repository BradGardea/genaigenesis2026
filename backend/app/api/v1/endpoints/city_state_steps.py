from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.city_state_step_models import CityStateStepResponse
from app.services import city_state_steps_service

router = APIRouter(prefix="/information/city-state", tags=["information-city-state"])


@router.get("/current-step", response_model=CityStateStepResponse)
async def get_city_state_current_step(
    step: int = Query(..., ge=0, description="0-based city-state step index"),
    beautify: bool = Query(True, description="When false, skip OpenAI beautification"),
) -> CityStateStepResponse:
    try:
        return await city_state_steps_service.get_city_state_current_step(
            step, beautify=beautify
        )
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/next-step", response_model=CityStateStepResponse)
async def get_city_state_next_step(
    curr_step: int = Query(..., ge=0, description="0-based current city-state step index"),
    beautify: bool = Query(True, description="When false, skip OpenAI beautification"),
) -> CityStateStepResponse:
    return await city_state_steps_service.get_city_state_next_step(
        curr_step, beautify=beautify
    )
