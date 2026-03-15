from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.schemas.weather_step_models import (
    WeatherDatasetMetadata,
    WeatherStepCard,
    WeatherStepMeta,
    WeatherStepResponse,
)
from app.services.timestep_dataset import TimestepDataset
from app.utils.openai_weather_beautifier import beautify_weather_step

WEATHER_DATASET_FILENAME = "goma_severe_storm_12h_72_timesteps.json"
_WEATHER_RESPONSE_CACHE: dict[tuple[int, bool], WeatherStepResponse] = {}


@lru_cache(maxsize=1)
def _weather_dataset() -> TimestepDataset:
    root = Path(__file__).resolve().parents[3]
    return TimestepDataset(root / "data" / WEATHER_DATASET_FILENAME)


def _metadata_model() -> WeatherDatasetMetadata:
    metadata = _weather_dataset().metadata()
    return WeatherDatasetMetadata(
        dataset_name=str(metadata.get("dataset_name", WEATHER_DATASET_FILENAME)),
        version=str(metadata.get("version", "unknown")),
        generated_at=str(metadata.get("generated_at", "")),
        scenario_note=str(metadata.get("scenario_note", "")),
        location=metadata.get("location", {}),
        schema_alignment=metadata.get("schema_alignment", {}),
    )


async def _build_response(step_index: int, beautify: bool = True) -> WeatherStepResponse:
    cache_key = (step_index, beautify)
    if cache_key in _WEATHER_RESPONSE_CACHE:
        return _WEATHER_RESPONSE_CACHE[cache_key]

    dataset = _weather_dataset()
    step = dataset.get_step(step_index)
    beautified_cards = await beautify_weather_step(step, use_llm=beautify)
    step_time = str(step.get("time", ""))

    cards = [
        WeatherStepCard(
            id=f"weather-step-{step_index}-{index + 1}",
            headline=card["headline"],
            details=card["details"],
            severity=card["severity"],  # type: ignore[arg-type]
            conditionType=card.get("conditionType", "general"),  # type: ignore[arg-type]
            updatedAt=step_time,
            rawData=step,
        )
        for index, card in enumerate(beautified_cards)
    ]

    next_index = step_index + 1 if step_index < dataset.total_steps - 1 else None

    payload = WeatherStepResponse(
        metadata=_metadata_model(),
        step=WeatherStepMeta(
            step_index=step_index,
            step_time=step_time,
            total_steps=dataset.total_steps,
            has_next=next_index is not None,
            next_step_index=next_index,
        ),
        beautified=cards,
        raw=step,
    )
    _WEATHER_RESPONSE_CACHE[cache_key] = payload
    return payload


async def get_weather_current_step(step: int, beautify: bool = True) -> WeatherStepResponse:
    return await _build_response(step, beautify=beautify)


async def get_weather_next_step(
    curr_step: int, beautify: bool = True
) -> WeatherStepResponse:
    next_step = _weather_dataset().get_next_step_index(curr_step)
    return await _build_response(next_step, beautify=beautify)
