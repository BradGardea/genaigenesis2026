from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.schemas.city_state_step_models import (
    CityStateAlert,
    CityStateDatasetMetadata,
    CityStateStepCard,
    CityStateStepResponse,
)
from app.schemas.weather_step_models import WeatherStepMeta
from app.services.timestep_dataset import TimestepDataset
from app.services.city_state_augmentor import augment_city_state_step, maybe_inject_route_hazard
from app.utils.openai_city_state_alert_extractor import (
    extract_city_state_alerts_and_cards,
)

CITY_STATE_DATASET_FILENAME = "goma_severe_storm_12h_72_timesteps_city_state.json"
_CITY_STATE_RESPONSE_CACHE: dict[tuple[int, bool], CityStateStepResponse] = {}


@lru_cache(maxsize=1)
def _city_state_dataset() -> TimestepDataset:
    root = Path(__file__).resolve().parents[3]
    return TimestepDataset(root / "data" / CITY_STATE_DATASET_FILENAME)


def _metadata_model() -> CityStateDatasetMetadata:
    metadata = _city_state_dataset().metadata()
    return CityStateDatasetMetadata(
        dataset_name=str(metadata.get("dataset_name", CITY_STATE_DATASET_FILENAME)),
        version=str(metadata.get("version", "unknown")),
        generated_at=str(metadata.get("generated_at", "")),
        scenario_note=str(metadata.get("scenario_note", "")),
        location=metadata.get("location", {}),
        schema_alignment=metadata.get("schema_alignment", {}),
    )


async def _build_response(step_index: int, beautify: bool = True) -> CityStateStepResponse:
    cache_key = (step_index, beautify)
    if cache_key in _CITY_STATE_RESPONSE_CACHE:
        return _CITY_STATE_RESPONSE_CACHE[cache_key]

    dataset = _city_state_dataset()
    raw_step = dataset.get_step(step_index)
    step = augment_city_state_step(raw_step, step_index=step_index, total_steps=dataset.total_steps)
    await maybe_inject_route_hazard(
        step,
        step_index=step_index,
        total_steps=dataset.total_steps,
    )
    transformed = await extract_city_state_alerts_and_cards(step, use_llm=beautify)
    step_time = str(step.get("time", ""))

    cards = [
        CityStateStepCard(
            id=f"city-state-step-{step_index}-{index + 1}",
            headline=card["headline"],
            details=card["details"],
            severity=card["severity"],  # type: ignore[arg-type]
            updatedAt=step_time,
            rawData=step,
        )
        for index, card in enumerate(transformed["cards"])
    ]
    alerts = [
        CityStateAlert(
            id=f"city-alert-{step_index}-{index + 1}",
            title=alert["title"],
            details=alert["details"],
            urgency=alert["urgency"],  # type: ignore[arg-type]
            category=alert["category"],
            occurredAt=step_time,
            updatedAt=step_time,
            area=alert["area"],
            source=alert["source"],
            rawData=step,
        )
        for index, alert in enumerate(transformed["alerts"])
    ]

    next_index = step_index + 1 if step_index < dataset.total_steps - 1 else None
    payload = CityStateStepResponse(
        metadata=_metadata_model(),
        step=WeatherStepMeta(
            step_index=step_index,
            step_time=step_time,
            total_steps=dataset.total_steps,
            has_next=next_index is not None,
            next_step_index=next_index,
        ),
        beautified=cards,
        alerts=alerts,
        raw=step,
    )
    _CITY_STATE_RESPONSE_CACHE[cache_key] = payload
    return payload


async def get_city_state_current_step(step: int, beautify: bool = True) -> CityStateStepResponse:
    return await _build_response(step, beautify=beautify)


async def get_city_state_next_step(
    curr_step: int, beautify: bool = True
) -> CityStateStepResponse:
    next_step = _city_state_dataset().get_next_step_index(curr_step)
    return await _build_response(next_step, beautify=beautify)
