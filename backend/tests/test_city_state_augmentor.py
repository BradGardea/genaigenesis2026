from __future__ import annotations

import asyncio

from app.services.city_state_augmentor import (
    TARGET_FLOOD_START_STEP,
    TARGET_ROUTE_LOCK_STEP,
    augment_city_state_step,
    maybe_inject_route_hazard,
)
from app.services.hazard_store import hazard_store


def _raw_step() -> dict:
    return {
        "time": "2026-03-14T00:00:00Z",
        "city_state": {},
    }


def _clear_store() -> None:
    hazard_store._hazards.clear()
    hazard_store._zones.clear()
    hazard_store._routes.clear()


def _register_route() -> None:
    hazard_store.register_route(
        route_id="route-test",
        origin=(29.18, -1.68),
        destination=(29.28, -1.67),
        geometry_geojson={
            "type": "LineString",
            "coordinates": [[29.18, -1.68], [29.23, -1.675], [29.28, -1.67]],
        },
    )


def test_background_noise_grows_every_third_step() -> None:
    step_zero = augment_city_state_step(_raw_step(), step_index=0, total_steps=72)
    step_six = augment_city_state_step(_raw_step(), step_index=6, total_steps=72)

    step_zero_sources = {
        str(area.get("source_kind", ""))
        for area in step_zero["city_state"]["affected_areas"]
    }
    assert any(source.startswith("simulated_background_rain") for source in step_zero_sources)
    assert any(source.startswith("simulated_background_high_wind") for source in step_zero_sources)
    assert any(
        any(str(ref).startswith("focus:offroute:") for ref in area.get("source_refs", []))
        for area in step_zero["city_state"]["affected_areas"]
    )
    assert step_zero["city_state"]["overall_severity"] < step_six["city_state"]["overall_severity"]
    assert step_six["city_state"]["impact_summary"]["flooding_points"] >= step_zero["city_state"]["impact_summary"]["flooding_points"]


def test_route_focus_generates_flood_by_target_window() -> None:
    _clear_store()
    _register_route()

    augmented = augment_city_state_step(_raw_step(), step_index=TARGET_FLOOD_START_STEP, total_steps=72)
    floods = [
        area
        for area in augmented["city_state"]["affected_areas"]
        if area.get("impact_type") == "flooding"
    ]

    assert any(area.get("source_kind") == "simulated_target_flood" for area in floods)
    assert not any(area.get("impact_type") == "road_closure" for area in augmented["city_state"]["affected_areas"])

    _clear_store()


def test_route_closure_appears_by_lock_step_and_injects_hazard() -> None:
    _clear_store()
    _register_route()

    augmented = augment_city_state_step(_raw_step(), step_index=TARGET_ROUTE_LOCK_STEP, total_steps=72)
    closures = [
        area
        for area in augmented["city_state"]["affected_areas"]
        if area.get("impact_type") == "road_closure"
    ]

    assert any(area.get("source_kind") == "simulated_target_road_closure" for area in closures)

    asyncio.run(
        maybe_inject_route_hazard(
            augmented,
            step_index=TARGET_ROUTE_LOCK_STEP,
            total_steps=72,
        )
    )

    active_hazards = hazard_store.get_active_hazards()
    assert len(active_hazards) == 1
    assert active_hazards[0].hazard_type == "roadblock"

    _clear_store()
