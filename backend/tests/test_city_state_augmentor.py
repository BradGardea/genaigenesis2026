from app.services.city_state_augmentor import COASTLINE_ANCHORS, augment_city_state_step


def _raw_step() -> dict:
    return {
        "time": "2026-03-14T00:00:00Z",
        "city_state": {
            "overall_severity": 40,
            "affected_areas": [
                {
                    "lat": COASTLINE_ANCHORS[1][0],
                    "lon": COASTLINE_ANCHORS[1][1],
                    "impact_type": "rain",
                    "severity": 52,
                    "radius_m": 180,
                    "status": "persistent",
                },
                {
                    "lat": COASTLINE_ANCHORS[4][0],
                    "lon": COASTLINE_ANCHORS[4][1],
                    "impact_type": "high_wind",
                    "severity": 56,
                    "radius_m": 200,
                    "status": "persistent",
                },
            ],
        },
    }


def test_coastal_seeds_drift_inland_across_steps() -> None:
    raw_step = _raw_step()
    step_zero = augment_city_state_step(_raw_step(), step_index=0, total_steps=72)
    step_ten = augment_city_state_step(_raw_step(), step_index=10, total_steps=72)

    initial_seeds = [
        area for area in step_zero["city_state"]["affected_areas"] if area.get("source_kind") == "seed_coast_protected"
    ]
    inland_seeds = [
        area for area in step_ten["city_state"]["affected_areas"] if area.get("source_kind") == "seed_coast_protected"
    ]

    assert len(initial_seeds) == 2
    assert len(inland_seeds) == 2

    initial_by_seed = {tuple(area.get("source_refs", [])): area for area in initial_seeds}
    inland_by_seed = {tuple(area.get("source_refs", [])): area for area in inland_seeds}

    for seed_key, initial in initial_by_seed.items():
        inland = inland_by_seed[seed_key]
        seed_index = int(seed_key[0].split(":")[1])
        raw_seed = raw_step["city_state"]["affected_areas"][seed_index]
        assert initial["lon"] < raw_seed["lon"]
        assert inland["lon"] > initial["lon"]


def test_generator_no_longer_uses_route_corridor_source_kinds() -> None:
    augmented = augment_city_state_step(_raw_step(), step_index=0, total_steps=72)
    source_kinds = {str(area.get("source_kind", "")) for area in augmented["city_state"]["affected_areas"]}
    source_refs = {
        ref
        for area in augmented["city_state"]["affected_areas"]
        for ref in area.get("source_refs", [])
    }

    assert "generated_corridor" not in source_kinds
    assert "placement:corridor" not in source_refs


def test_seed_frontier_is_wider_and_persists_for_thirty_steps() -> None:
    step_ten = augment_city_state_step(_raw_step(), step_index=10, total_steps=72)
    step_thirty_one = augment_city_state_step(_raw_step(), step_index=31, total_steps=72)

    protected_frontier = [
        area for area in step_ten["city_state"]["affected_areas"] if str(area.get("source_kind", "")).endswith("_protected")
    ]
    late_protected_frontier = [
        area
        for area in step_thirty_one["city_state"]["affected_areas"]
        if str(area.get("source_kind", "")).endswith("_protected")
    ]

    assert len(protected_frontier) == 6
    assert len(late_protected_frontier) == 0


def test_seed_drift_children_keep_seed_lineage_and_move_farther_inland() -> None:
    seed_parent = None
    seed_child = None

    for step_index in range(1, 16):
        augmented = augment_city_state_step(_raw_step(), step_index=step_index, total_steps=72)
        affected_areas = augmented["city_state"]["affected_areas"]
        seed_parent = next(
            area
            for area in affected_areas
            if area.get("source_kind") == "seed_coast_protected" and area.get("impact_type") == "rain"
        )
        seed_child = next(
            (
                area
                for area in affected_areas
                if area.get("source_kind") == "propagated_seed_drift" and "seed:0" in area.get("source_refs", [])
            ),
            None,
        )
        if seed_child is not None:
            break

    assert seed_parent is not None
    assert seed_child is not None
    assert "seed:0" in seed_child["source_refs"]
    assert seed_child["lon"] > seed_parent["lon"]


def test_front_based_generation_uses_new_storm_track_sources() -> None:
    augmented = augment_city_state_step(_raw_step(), step_index=0, total_steps=72)
    source_kinds = {str(area.get("source_kind", "")) for area in augmented["city_state"]["affected_areas"]}

    assert any(source_kind.startswith("generated_front_") for source_kind in source_kinds)
