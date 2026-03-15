from __future__ import annotations

import hashlib
import math
import random
from copy import deepcopy
from typing import Any

from app.models.routing import HazardReport
from app.services.hazard_store import hazard_store

BASE_SEED = 20260314
DEFAULT_CITY_CENTER = (-22.000, 35.320)
DEFAULT_ROUTE_SPAN_M = 4_000.0
NOISE_RADIUS_MULTIPLIER = 1.3
NOISE_GROWTH_EVERY_STEPS = 3
BASE_NOISE_POINTS_PER_TYPE = 5
NOISE_POINTS_PER_GROWTH = 2
FOCUS_ACCELERATION_START_STEP = 24
TARGET_FLOOD_START_STEP = 38
TARGET_ROUTE_LOCK_STEP = 45
ROAD_CLOSURE_PERSISTENCE_STEPS = 5
FOCUS_ROUTE_FRACTION = 0.62
FLOOD_LINK_DISTANCE_M = 340.0
FLOOD_NEIGHBORHOOD_DISTANCE_M = 260.0
FLOOD_RAIN_NEIGHBORS_REQUIRED = 4
FLOOD_WIND_SUPPORT_REQUIRED = 1
ROAD_CLOSURE_TRIGGER_SCORE = 84.0
OFF_ROUTE_CLUSTER_COUNT = 3
OFF_ROUTE_CLUSTER_BASE_POINTS = 2
WIND_TO_RAIN_RATIO = 3
MAX_FLOODS_PER_STEP = 18
MAX_CLOSURES_PER_STEP = 10
MAX_AFFECTED_AREAS = 120

_INJECTED_ROUTE_HAZARDS: set[tuple[str, str]] = set()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _offset_lat_lon(lat: float, lon: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    lat_offset = dy_m / 111_320.0
    lon_offset = dx_m / max(111_320.0 * math.cos(math.radians(lat)), 1e-6)
    return lat + lat_offset, lon + lon_offset


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 111_320.0
    dx = (lon2 - lon1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _danger_from_severity(overall: int) -> str:
    if overall >= 85:
        return "extreme"
    if overall >= 65:
        return "high"
    if overall >= 35:
        return "moderate"
    return "low"


def _status_from_severity(overall: int) -> str:
    if overall >= 85:
        return "critical_failure"
    if overall >= 65:
        return "severe_disruption"
    if overall >= 35:
        return "constrained_operations"
    return "degraded_operations"


def _impact_priority(impact_type: str) -> int:
    priorities = {
        "road_closure": 5,
        "flooding": 4,
        "structure_damage": 3,
        "high_wind": 3,
        "rain": 2,
        "debris": 1,
    }
    return priorities.get(impact_type, 0)


def _seeded_random(seed_key: str, step_index: int, salt: str) -> random.Random:
    digest = hashlib.sha256(f"{seed_key}:{step_index}:{salt}:{BASE_SEED}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _route_context() -> dict[str, Any]:
    routes = list(hazard_store._routes.values())
    if routes:
        sub = routes[-1]
        start_lon, start_lat = sub.origin
        end_lon, end_lat = sub.destination
        target = sub.geometry.interpolate(FOCUS_ROUTE_FRACTION, normalized=True)
        return {
            "seed_key": sub.route_id,
            "start": (float(start_lat), float(start_lon)),
            "end": (float(end_lat), float(end_lon)),
            "target": (float(target.y), float(target.x)),
            "distance_m": _distance_m(float(start_lat), float(start_lon), float(end_lat), float(end_lon)),
            "route_id": sub.route_id,
        }

    start = _offset_lat_lon(DEFAULT_CITY_CENTER[0], DEFAULT_CITY_CENTER[1], -DEFAULT_ROUTE_SPAN_M * 0.45, -240)
    end = _offset_lat_lon(DEFAULT_CITY_CENTER[0], DEFAULT_CITY_CENTER[1], DEFAULT_ROUTE_SPAN_M * 0.55, 210)
    target = (
        start[0] + (end[0] - start[0]) * FOCUS_ROUTE_FRACTION,
        start[1] + (end[1] - start[1]) * FOCUS_ROUTE_FRACTION,
    )
    return {
        "seed_key": "fallback-route",
        "start": start,
        "end": end,
        "target": target,
        "distance_m": _distance_m(start[0], start[1], end[0], end[1]),
        "route_id": None,
    }


def _interpolate_point(start: tuple[float, float], end: tuple[float, float], fraction: float) -> tuple[float, float]:
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    )


def _route_side_cluster_centers(
    start: tuple[float, float],
    end: tuple[float, float],
    seed_key: str,
) -> list[tuple[float, float]]:
    dx_m = (end[1] - start[1]) * 111_320.0 * math.cos(math.radians((start[0] + end[0]) / 2))
    dy_m = (end[0] - start[0]) * 111_320.0
    length = math.hypot(dx_m, dy_m) or 1.0
    normal_x = -dy_m / length
    normal_y = dx_m / length
    tangent_x = dx_m / length
    tangent_y = dy_m / length

    centers: list[tuple[float, float]] = []
    for idx, fraction in enumerate((0.24, 0.52, 0.78), start=1):
        rnd = _seeded_random(seed_key, idx, "off-route-center")
        base = _interpolate_point(start, end, fraction)
        side = -1.0 if idx % 2 == 0 else 1.0
        offset_m = rnd.uniform(700.0, 1_600.0) * side
        drift_m = rnd.uniform(-300.0, 320.0)
        centers.append(
            _offset_lat_lon(
                base[0],
                base[1],
                normal_x * offset_m + tangent_x * drift_m,
                normal_y * offset_m + tangent_y * drift_m,
            )
        )
    return centers


def _event(
    *,
    lat: float,
    lon: float,
    impact_type: str,
    severity: int,
    radius_m: int,
    status: str,
    source_kind: str,
    source_refs: list[str] | None = None,
    node_id: str | None = None,
    cluster_size: int | None = None,
) -> dict[str, Any]:
    sev = int(_clamp(severity, 5, 100))
    area: dict[str, Any] = {
        "node_id": node_id,
        "lat": lat,
        "lon": lon,
        "impact_type": impact_type,
        "severity": sev,
        "danger_to_remain": _danger_from_severity(sev),
        "status": status,
        "radius_m": int(_clamp(radius_m, 60, 1_200)),
        "source_kind": source_kind,
        "source_refs": source_refs or [],
    }
    if cluster_size is not None:
        area["cluster_size"] = cluster_size
    return area


def _sample_disk_point(center: tuple[float, float], radius_m: float, rnd: random.Random) -> tuple[float, float]:
    theta = rnd.uniform(0.0, math.tau)
    dist = math.sqrt(rnd.random()) * radius_m
    return _offset_lat_lon(center[0], center[1], math.cos(theta) * dist, math.sin(theta) * dist)


def _growth_level(step_index: int) -> int:
    return step_index // NOISE_GROWTH_EVERY_STEPS


def _route_pressure(step_index: int) -> float:
    early = _clamp(step_index / max(TARGET_FLOOD_START_STEP, 1), 0.0, 1.0) * 0.35
    late = _clamp(
        (step_index - FOCUS_ACCELERATION_START_STEP)
        / max(TARGET_ROUTE_LOCK_STEP - FOCUS_ACCELERATION_START_STEP, 1),
        0.0,
        1.0,
    )
    return max(early, late)


def _derive_floods(
    rain_events: list[dict[str, Any]],
    wind_events: list[dict[str, Any]],
    *,
    step_index: int,
    route_target: tuple[float, float],
) -> list[dict[str, Any]]:
    floods: list[dict[str, Any]] = []
    pressure = _route_pressure(step_index)
    seen_cells: set[tuple[int, int, str]] = set()

    for rain in rain_events:
        rain_neighbors = [
            candidate
            for candidate in rain_events
            if _distance_m(
                float(rain["lat"]),
                float(rain["lon"]),
                float(candidate["lat"]),
                float(candidate["lon"]),
            )
            <= FLOOD_NEIGHBORHOOD_DISTANCE_M
        ]
        if len(rain_neighbors) < FLOOD_RAIN_NEIGHBORS_REQUIRED:
            continue

        support_winds = [
            wind
            for wind in wind_events
            if _distance_m(
                float(rain["lat"]),
                float(rain["lon"]),
                float(wind["lat"]),
                float(wind["lon"]),
            )
            <= FLOOD_LINK_DISTANCE_M
        ]
        if len(support_winds) < FLOOD_WIND_SUPPORT_REQUIRED:
            continue

        focus_lineage = any("focus:route" in item.get("source_refs", []) for item in rain_neighbors) or any(
            "focus:route" in item.get("source_refs", []) for item in support_winds
        )
        cell_key = (
            int(float(rain["lat"]) * 4_000),
            int(float(rain["lon"]) * 4_000),
            "target" if focus_lineage else "general",
        )
        if cell_key in seen_cells:
            continue
        seen_cells.add(cell_key)

        mean_rain = sum(int(item["severity"]) for item in rain_neighbors) / len(rain_neighbors)
        mean_wind = sum(int(item["severity"]) for item in support_winds) / len(support_winds)
        density_bonus = len(rain_neighbors) * 2.5
        pressure_bonus = 18.0 * pressure if focus_lineage else 0.0
        flood_score = mean_rain * 0.88 + mean_wind * 0.34 + density_bonus + pressure_bonus

        lat = sum(float(item["lat"]) for item in rain_neighbors) / len(rain_neighbors)
        lon = sum(float(item["lon"]) for item in rain_neighbors) / len(rain_neighbors)
        if focus_lineage:
            lat, lon = route_target

        floods.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type="flooding",
                severity=int(_clamp(flood_score, 35, 100)),
                radius_m=int(_clamp(150 + len(rain_neighbors) * 22 + len(support_winds) * 14, 140, 700)),
                status="worsening" if focus_lineage else "new",
                source_kind="simulated_target_flood" if focus_lineage else "simulated_flood",
                source_refs=sorted(
                    {
                        *[ref for item in rain_neighbors for ref in item.get("source_refs", [])],
                        *[ref for item in support_winds for ref in item.get("source_refs", [])],
                    }
                ),
                node_id=f"flood-{abs(int(lat * 1e6))}-{abs(int(lon * 1e6))}",
                cluster_size=len(rain_neighbors),
            )
        )

    focus_rains = [event for event in rain_events if "focus:route" in event.get("source_refs", [])]
    focus_winds = [event for event in wind_events if "focus:route" in event.get("source_refs", [])]
    if len(focus_rains) >= FLOOD_RAIN_NEIGHBORS_REQUIRED and len(focus_winds) >= FLOOD_WIND_SUPPORT_REQUIRED:
        mean_rain = sum(int(item["severity"]) for item in focus_rains) / len(focus_rains)
        mean_wind = sum(int(item["severity"]) for item in focus_winds) / len(focus_winds)
        flood_score = mean_rain * 0.9 + mean_wind * 0.38 + len(focus_rains) * 2.2 + 20.0 * pressure
        floods.append(
            _event(
                lat=route_target[0],
                lon=route_target[1],
                impact_type="flooding",
                severity=max(95, int(_clamp(flood_score, 40, 100))),
                radius_m=int(_clamp(170 + len(focus_rains) * 20 + len(focus_winds) * 16, 160, 760)),
                status="worsening",
                source_kind="simulated_target_flood",
                source_refs=sorted(
                    {
                        *[ref for item in focus_rains for ref in item.get("source_refs", [])],
                        *[ref for item in focus_winds for ref in item.get("source_refs", [])],
                    }
                ),
                node_id=f"flood-target-{abs(int(route_target[0] * 1e6))}-{abs(int(route_target[1] * 1e6))}",
                cluster_size=len(focus_rains),
            )
        )

    # Only keep floods that reach "high" severity (>= 65).
    floods = [item for item in floods if int(item["severity"]) >= 65]

    target_floods = [item for item in floods if item.get("source_kind") == "simulated_target_flood"]
    non_target = [item for item in floods if item.get("source_kind") != "simulated_target_flood"]
    non_target.sort(key=lambda item: int(item["severity"]), reverse=True)
    kept = target_floods[:1] + non_target[: max(0, MAX_FLOODS_PER_STEP - len(target_floods[:1]))]
    kept.sort(key=lambda item: int(item["severity"]), reverse=True)
    return kept


def _derive_route_closures(
    floods: list[dict[str, Any]],
    *,
    step_index: int,
) -> list[dict[str, Any]]:
    closures: list[dict[str, Any]] = []

    # Road closures appear immediately whenever a flood object exists.
    for flood in floods:
        closure_score = int(flood["severity"])

        node_seed = str(flood.get("node_id", "flood"))
        rnd = _seeded_random(node_seed, step_index, "road-closure")
        angle = rnd.uniform(0.0, math.tau)
        distance_m = rnd.uniform(0.0, max(float(flood["radius_m"]) * 0.45, 20.0))
        lat, lon = _offset_lat_lon(
            float(flood["lat"]),
            float(flood["lon"]),
            math.cos(angle) * distance_m,
            math.sin(angle) * distance_m,
        )

        closures.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type="road_closure",
                severity=max(78, int(_clamp(closure_score, 78, 100))),
                radius_m=int(_clamp(int(flood["radius_m"]) * 0.58, 100, 320)),
                status="new",
                source_kind="simulated_target_road_closure"
                if flood.get("source_kind") == "simulated_target_flood"
                else "simulated_road_closure",
                source_refs=[*flood.get("source_refs", []), str(flood.get("node_id", "")), "route-lock"],
                node_id=f"closure-{step_index}-{abs(int(lat * 1e6))}-{abs(int(lon * 1e6))}",
            )
        )

    target_closures = [item for item in closures if item.get("source_kind") == "simulated_target_road_closure"]
    non_target = [item for item in closures if item.get("source_kind") != "simulated_target_road_closure"]
    non_target.sort(key=lambda item: int(item["severity"]), reverse=True)
    kept = target_closures[:1] + non_target[: max(0, MAX_CLOSURES_PER_STEP - len(target_closures[:1]))]
    kept.sort(key=lambda item: int(item["severity"]), reverse=True)
    return kept


def _recompute_metadata(city_state: dict[str, Any]) -> None:
    areas = city_state.get("affected_areas", []) if isinstance(city_state.get("affected_areas"), list) else []
    summary = {
        "affected_points": len(areas),
        "rain_points": 0,
        "high_wind_points": 0,
        "flooding_points": 0,
        "road_closure_points": 0,
        "debris_points": 0,
        "structure_damage_points": 0,
    }
    weighted = 0.0
    dominant_counts: dict[str, int] = {}
    for area in areas:
        impact_type = str(area.get("impact_type", "other"))
        key = f"{impact_type}_points"
        summary[key] = int(summary.get(key, 0)) + 1
        dominant_counts[impact_type] = dominant_counts.get(impact_type, 0) + 1
        multiplier = {
            "rain": 0.75,
            "high_wind": 0.85,
            "flooding": 1.1,
            "road_closure": 1.35,
            "debris": 0.9,
            "structure_damage": 1.2,
        }.get(impact_type, 0.7)
        weighted += int(area.get("severity", 0)) * multiplier

    max_severity = max((int(area.get("severity", 0)) for area in areas), default=0)
    closures = int(summary.get("road_closure_points", 0))
    floods = int(summary.get("flooding_points", 0))
    overall = int(
        _clamp(
            max_severity * 0.45 + weighted / max(len(areas), 1) * 0.55 + floods * 2.0 + closures * 8.0,
            5,
            100,
        )
    )

    city_state["impact_summary"] = summary
    city_state["overall_severity"] = overall
    city_state["danger_to_remain"] = _danger_from_severity(overall)
    city_state["operational_status"] = _status_from_severity(overall)
    city_state["dominant_impacts"] = [
        impact for impact, _count in sorted(dominant_counts.items(), key=lambda item: (item[1], _impact_priority(item[0])), reverse=True)[:3]
    ]

    if closures > 0:
        action = "Reroute immediately around the closure corridor and avoid the flooded segment."
    elif floods > 0:
        action = "Prepare alternate routing; flood conditions are building along the evacuation corridor."
    elif int(summary.get("high_wind_points", 0)) > 0:
        action = "Continue evacuation with caution as wind and rain cells begin to organize."
    else:
        action = "Monitor the route; sparse rain and wind noise is beginning to spread."

    city_state["recommended_action"] = action
    city_state["city_services"] = {
        "roads": "reroute_required" if closures > 0 else ("flood_watch" if floods > 0 else "open_with_delays"),
        "power": "unstable" if overall >= 70 else "operational",
        "dispatch": "strained" if overall >= 60 else "active",
    }


def augment_city_state_step(raw_step: dict[str, Any], step_index: int, total_steps: int) -> dict[str, Any]:
    step = deepcopy(raw_step)
    city_state = step.get("city_state") if isinstance(step.get("city_state"), dict) else {}
    city_state = deepcopy(city_state)

    context = _route_context()
    start = context["start"]
    end = context["end"]
    target = context["target"]
    distance_m = max(float(context["distance_m"]), 1.0)
    circle_radius_m = max(1_500.0, distance_m * NOISE_RADIUS_MULTIPLIER)
    growth = _growth_level(step_index)
    progress = step_index / max(total_steps - 1, 1)
    pressure = _route_pressure(step_index)
    seed_key = str(context["seed_key"])

    rain_raw: list[dict[str, Any]] = []
    wind_raw: list[dict[str, Any]] = []

    background_rain_points = BASE_NOISE_POINTS_PER_TYPE + growth * NOISE_POINTS_PER_GROWTH
    background_wind_points = max(1, background_rain_points // WIND_TO_RAIN_RATIO)

    rain_rnd = _seeded_random(seed_key, step_index, "rain")
    for idx in range(background_rain_points):
        lat, lon = _sample_disk_point(start, circle_radius_m, rain_rnd)
        rain_raw.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type="rain",
                severity=int(16 + growth * 4 + progress * 10 + idx * 0.35 + 1.18 * step_index + rain_rnd.uniform(-4, 5)),
                radius_m=int(90 + growth * 10 + rain_rnd.uniform(0, 45)),
                status="new" if step_index == 0 else "persistent",
                source_kind="simulated_background_rain",
                source_refs=[f"noise:ring:{idx}"],
                node_id=f"rain-{step_index}-{idx}",
            )
        )

    wind_rnd = _seeded_random(seed_key, step_index, "high_wind")
    for idx in range(background_wind_points):
        lat, lon = _sample_disk_point(start, circle_radius_m, wind_rnd)
        wind_raw.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type="high_wind",
                severity=int(19 + growth * 3 + progress * 8 + idx * 0.2 + 0.88 * step_index + wind_rnd.uniform(-4, 4)),
                radius_m=int(95 + growth * 8 + wind_rnd.uniform(0, 35)),
                status="new" if step_index == 0 else "persistent",
                source_kind="simulated_background_high_wind",
                source_refs=[f"noise:ring:{idx}"],
                node_id=f"wind-{step_index}-{idx}",
            )
        )

    side_cluster_centers = _route_side_cluster_centers(start, end, seed_key)[:OFF_ROUTE_CLUSTER_COUNT]
    for cluster_index, center in enumerate(side_cluster_centers):
        cluster_rnd = _seeded_random(seed_key, step_index, f"off-route-cluster:{cluster_index}")
        cluster_points = OFF_ROUTE_CLUSTER_BASE_POINTS + growth // 2 + cluster_index % 2
        cluster_spread_m = max(120.0, 260.0 - growth * 6.0)
        for point_index in range(cluster_points):
            sample_lat, sample_lon = _sample_disk_point(center, cluster_spread_m, cluster_rnd)
            rain_raw.append(
                _event(
                    lat=sample_lat,
                    lon=sample_lon,
                    impact_type="rain",
                    severity=int(18 + 1.02 * step_index + growth * 3 + cluster_rnd.uniform(-4, 4)),
                    radius_m=int(105 + growth * 8 + cluster_rnd.uniform(0, 40)),
                    status="persistent" if step_index > 0 else "new",
                    source_kind="simulated_offroute_rain",
                    source_refs=[f"focus:offroute:{cluster_index}", f"cluster:{point_index}"],
                    node_id=f"offroute-rain-{cluster_index}-{point_index}",
                )
            )
            if point_index % WIND_TO_RAIN_RATIO == 0:
                wind_raw.append(
                    _event(
                        lat=sample_lat,
                        lon=sample_lon,
                        impact_type="high_wind",
                        severity=int(20 + 0.86 * step_index + growth * 2 + cluster_rnd.uniform(-4, 4)),
                        radius_m=int(105 + growth * 7 + cluster_rnd.uniform(0, 32)),
                        status="persistent" if step_index > 0 else "new",
                        source_kind="simulated_offroute_high_wind",
                        source_refs=[f"focus:offroute:{cluster_index}", f"cluster:{point_index}"],
                        node_id=f"offroute-wind-{cluster_index}-{point_index}",
                    )
                )

    focus_rain_points = 2 + min(9, int(pressure * 9))
    focus_wind_points = max(1, math.ceil(focus_rain_points / WIND_TO_RAIN_RATIO))
    focus_spread_m = max(70.0, 240.0 - pressure * 150.0)
    focus_rnd = _seeded_random(seed_key, step_index, "route-focus")

    for idx in range(focus_rain_points):
        focus_lat, focus_lon = _sample_disk_point(target, focus_spread_m, focus_rnd)
        rain_raw.append(
            _event(
                lat=focus_lat,
                lon=focus_lon,
                impact_type="rain",
                severity=int(24 + step_index * 1.0 + pressure * 30 + focus_rnd.uniform(-2, 5)),
                radius_m=int(110 + pressure * 75 + focus_rnd.uniform(0, 30)),
                status="worsening" if pressure > 0.2 else "new",
                source_kind="simulated_route_focus_rain",
                source_refs=["focus:route", f"focus:{idx}"],
                node_id=f"focus-rain-{step_index}-{idx}",
            )
        )

    for idx in range(focus_wind_points):
        focus_lat, focus_lon = _sample_disk_point(target, focus_spread_m, focus_rnd)
        wind_raw.append(
            _event(
                lat=focus_lat,
                lon=focus_lon,
                impact_type="high_wind",
                severity=int(22 + step_index * 0.74 + pressure * 18 + focus_rnd.uniform(-2, 4)),
                radius_m=int(100 + pressure * 55 + focus_rnd.uniform(0, 22)),
                status="worsening" if pressure > 0.2 else "new",
                source_kind="simulated_route_focus_wind",
                source_refs=["focus:route", f"focus:{idx}"],
                node_id=f"focus-wind-{step_index}-{idx}",
            )
        )

    # Derive secondary impacts (debris + structure damage)
    secondary_rnd = _seeded_random(seed_key, step_index, "secondary-impacts")
    secondary_raw: list[dict[str, Any]] = []
    for event in rain_raw + wind_raw:
        sev = int(event["severity"])
        if secondary_rnd.random() < 0.10:
            dx = secondary_rnd.uniform(-80, 80)
            dy = secondary_rnd.uniform(-80, 80)
            d_lat, d_lon = _offset_lat_lon(float(event["lat"]), float(event["lon"]), dx, dy)
            secondary_raw.append(_event(
                lat=d_lat, lon=d_lon,
                impact_type="debris",
                severity=int(_clamp(sev * 0.7 + secondary_rnd.uniform(-5, 10), 15, 90)),
                radius_m=int(70 + secondary_rnd.uniform(0, 40)),
                status=event["status"],
                source_kind="simulated_debris",
                source_refs=event.get("source_refs", []),
                node_id=f"debris-{step_index}-{abs(int(d_lat * 1e6))}-{abs(int(d_lon * 1e6))}",
            ))
        if secondary_rnd.random() < 0.03:
            dx = secondary_rnd.uniform(-60, 60)
            dy = secondary_rnd.uniform(-60, 60)
            s_lat, s_lon = _offset_lat_lon(float(event["lat"]), float(event["lon"]), dx, dy)
            secondary_raw.append(_event(
                lat=s_lat, lon=s_lon,
                impact_type="structure_damage",
                severity=int(_clamp(sev * 0.8 + secondary_rnd.uniform(-3, 15), 20, 95)),
                radius_m=int(50 + secondary_rnd.uniform(0, 30)),
                status=event["status"],
                source_kind="simulated_structure_damage",
                source_refs=event.get("source_refs", []),
                node_id=f"struct-{step_index}-{abs(int(s_lat * 1e6))}-{abs(int(s_lon * 1e6))}",
            ))

    floods = _derive_floods(rain_raw, wind_raw, step_index=step_index, route_target=target)
    closures = _derive_route_closures(floods, step_index=step_index)

    areas = rain_raw + wind_raw + floods + closures + secondary_raw
    areas.sort(key=lambda area: (_impact_priority(str(area.get("impact_type", ""))), int(area.get("severity", 0))), reverse=True)
    city_state["affected_areas"] = areas[:MAX_AFFECTED_AREAS]
    _recompute_metadata(city_state)
    city_state["note"] = (
        "Synthetic route-pressure simulation active. Rain persists throughout the timeline, "
        f"wind remains sparse (~{WIND_TO_RAIN_RATIO}:1 rain-to-wind), floods are additive over dense rain pockets, "
        f"and road closures appear about {ROAD_CLOSURE_PERSISTENCE_STEPS} steps after flood emergence."
    )

    step["city_state"] = city_state
    return step


async def maybe_inject_route_hazard(
    augmented_step: dict[str, Any],
    *,
    step_index: int,
    total_steps: int,
) -> None:
    del total_steps
    city_state = augmented_step.get("city_state")
    if not isinstance(city_state, dict):
        return

    closures = [
        area
        for area in city_state.get("affected_areas", [])
        if isinstance(area, dict) and area.get("impact_type") == "road_closure"
    ]
    if not closures:
        return

    routes = list(hazard_store._routes.values())
    if not routes:
        return

    closures.sort(
        key=lambda area: 1 if area.get("source_kind") == "simulated_target_road_closure" else 0,
        reverse=True,
    )

    for sub in routes:
        injected_for_route = False
        for closure in closures:
            node_id = str(closure.get("node_id") or f"closure-step-{step_index}")
            key = (sub.route_id, node_id)
            if key in _INJECTED_ROUTE_HAZARDS:
                continue

            report = HazardReport(
                hazard_type="roadblock",
                location={"lng": float(closure["lon"]), "lat": float(closure["lat"] )},
                radius_meters=float(closure.get("radius_m", 180)),
                description=f"Synthetic route closure injected at step {step_index}",
            )
            zone = hazard_store.add_hazard(report)
            affected = await hazard_store.notify_affected_routes(zone)
            if sub.route_id in affected:
                _INJECTED_ROUTE_HAZARDS.add(key)
                injected_for_route = True
                break
        if injected_for_route:
            continue
