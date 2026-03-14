from __future__ import annotations

import hashlib
import math
import random
from copy import deepcopy
from typing import Any

from app.models.routing import HazardReport
from app.services.hazard_store import hazard_store

ROUTE_ORIGIN = (-1.661392, 29.174324)  # (lat, lon)
ROUTE_DESTINATION = (-1.632659, 29.248804)  # (lat, lon)
CITY_CENTER = (-1.679, 29.222)
BASE_SEED = 20260314

# Low-frequency route hazard injection controls.
ROUTE_HAZARD_PROBABILITY = 0.05
ROUTE_HAZARD_STEP_COOLDOWN = 6
_INJECTED_ROUTE_STEPS: set[tuple[str, int]] = set()
_LAST_INJECTED_STEP_BY_ROUTE: dict[str, int] = {}


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


def _storm_intensity(progress: float) -> float:
    bell = math.exp(-((progress - 0.58) / 0.27) ** 2)
    pulse = 0.06 * math.sin(progress * math.pi * 4.5)
    return _clamp(0.35 + 0.75 * bell + pulse, 0.28, 1.12)


def _route_point(progress: float) -> tuple[float, float]:
    lat = ROUTE_ORIGIN[0] + (ROUTE_DESTINATION[0] - ROUTE_ORIGIN[0]) * progress
    lon = ROUTE_ORIGIN[1] + (ROUTE_DESTINATION[1] - ROUTE_ORIGIN[1]) * progress
    return lat, lon


def _route_unit_vectors() -> tuple[tuple[float, float], tuple[float, float]]:
    dy = (ROUTE_DESTINATION[0] - ROUTE_ORIGIN[0]) * 111_320.0
    avg_lat = (ROUTE_DESTINATION[0] + ROUTE_ORIGIN[0]) / 2
    dx = (ROUTE_DESTINATION[1] - ROUTE_ORIGIN[1]) * 111_320.0 * math.cos(math.radians(avg_lat))
    mag = math.hypot(dx, dy) or 1.0
    forward = (dx / mag, dy / mag)
    lateral = (-forward[1], forward[0])
    return forward, lateral


def _danger_from_severity(overall: int) -> str:
    if overall >= 85:
        return "extreme"
    if overall >= 70:
        return "high"
    if overall >= 45:
        return "moderate"
    return "low"


def _status_from_severity(overall: int) -> str:
    if overall >= 85:
        return "critical_failure"
    if overall >= 70:
        return "severe_disruption"
    if overall >= 45:
        return "constrained_operations"
    return "degraded_operations"


def _status_label(progress: float, rnd: random.Random) -> str:
    if progress < 0.25:
        return "new" if rnd.random() < 0.65 else "persistent"
    if progress < 0.7:
        return "worsening" if rnd.random() < 0.7 else "persistent"
    return "persistent" if rnd.random() < 0.7 else "worsening"


def _seeded_random(route_id: str, step_index: int) -> random.Random:
    digest = hashlib.sha256(f"{route_id}:{step_index}:{BASE_SEED}".encode("utf-8")).hexdigest()
    seed = int(digest[:16], 16)
    return random.Random(seed)


def _event(
    *,
    lat: float,
    lon: float,
    impact_type: str,
    severity: int,
    radius_m: int,
    status: str,
) -> dict[str, Any]:
    sev = int(_clamp(severity, 5, 100))
    return {
        "lat": lat,
        "lon": lon,
        "impact_type": impact_type,
        "severity": sev,
        "danger_to_remain": _danger_from_severity(sev),
        "status": status,
        "radius_m": int(_clamp(radius_m, 50, 1800)),
    }


def _is_low_danger(area: dict[str, Any]) -> bool:
    danger = str(area.get("danger_to_remain", "low")).lower()
    return danger not in {"high", "extreme"}


def _cluster_dense_overlaps(
    events: list[dict[str, Any]],
    *,
    impact_type: str,
    min_cluster_size: int = 10,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = [e for e in events if e.get("impact_type") == impact_type and _is_low_danger(e)]
    if len(candidates) < min_cluster_size:
        return events, []

    adjacency: dict[int, set[int]] = {i: set() for i in range(len(candidates))}
    for i in range(len(candidates)):
        a = candidates[i]
        for j in range(i + 1, len(candidates)):
            b = candidates[j]
            d = _distance_m(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]))
            overlap_threshold = 0.62 * (float(a["radius_m"]) + float(b["radius_m"]))
            if d <= overlap_threshold:
                adjacency[i].add(j)
                adjacency[j].add(i)

    visited: set[int] = set()
    clusters: list[list[int]] = []
    for i in range(len(candidates)):
        if i in visited:
            continue
        stack = [i]
        comp: list[int] = []
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            comp.append(node)
            stack.extend(adjacency[node] - visited)
        if len(comp) >= min_cluster_size:
            clusters.append(comp)

    if not clusters:
        return events, []

    to_remove_ids: set[int] = {id(candidates[idx]) for comp in clusters for idx in comp}
    merged_events: list[dict[str, Any]] = []

    for comp in clusters:
        group = [candidates[idx] for idx in comp]
        total_weight = sum(max(float(g["radius_m"]), 1.0) for g in group)
        center_lat = sum(float(g["lat"]) * max(float(g["radius_m"]), 1.0) for g in group) / total_weight
        center_lon = sum(float(g["lon"]) * max(float(g["radius_m"]), 1.0) for g in group) / total_weight
        max_radius = max(float(g["radius_m"]) for g in group)
        max_severity = max(int(g["severity"]) for g in group)

        merged_events.append(
            _event(
                lat=center_lat,
                lon=center_lon,
                impact_type=impact_type,
                severity=int(_clamp(max_severity + 8, 45, 88)),
                radius_m=int(_clamp(max_radius + math.sqrt(len(group)) * 120, 260, 1700)),
                status="merged_cluster",
            )
        )

    kept = [e for e in events if id(e) not in to_remove_ids]
    kept.extend(merged_events)
    return kept, merged_events


def _place_corridor_point(
    progress: float,
    intensity: float,
    forward: tuple[float, float],
    lateral: tuple[float, float],
    rnd: random.Random,
    *,
    ahead_bias: float = 0.0,
) -> tuple[float, float]:
    anchor_progress = _clamp(progress + rnd.uniform(-0.22, 0.20) + ahead_bias, 0.0, 1.0)
    a_lat, a_lon = _route_point(anchor_progress)
    along = rnd.uniform(-900, 1100) * (0.6 + 0.45 * intensity)
    side = rnd.uniform(-1100, 1100) * (0.55 + 0.4 * intensity)
    return _offset_lat_lon(
        a_lat,
        a_lon,
        along * forward[0] + side * lateral[0],
        along * forward[1] + side * lateral[1],
    )


def _ensure_spatial_separation(
    areas: list[dict[str, Any]], rnd: random.Random, min_distance_m: float = 90
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    for area in areas:
        lat = float(area["lat"])
        lon = float(area["lon"])
        impact = str(area.get("impact_type", "other"))
        tries = 0
        while tries < 6:
            too_close = False
            for kept in accepted:
                if str(kept.get("impact_type", "other")) != impact:
                    continue
                if _distance_m(lat, lon, float(kept["lat"]), float(kept["lon"])) < min_distance_m:
                    too_close = True
                    break
            if not too_close:
                break
            angle = rnd.uniform(0, 2 * math.pi)
            step = rnd.uniform(75, 170)
            lat, lon = _offset_lat_lon(lat, lon, step * math.cos(angle), step * math.sin(angle))
            tries += 1
        area["lat"] = lat
        area["lon"] = lon
        accepted.append(area)
    return accepted


def _recompute_metadata(
    city_state: dict[str, Any], original_overall: int, progress: float, intensity: float
) -> None:
    areas = city_state.get("affected_areas", [])
    if not isinstance(areas, list):
        areas = []

    counts = {
        "high_wind": 0,
        "flooding": 0,
        "road_closure": 0,
        "powerline_failure": 0,
        "debris": 0,
        "structure_damage": 0,
    }
    severities: list[int] = []

    for area in areas:
        impact_type = str(area.get("impact_type", "other"))
        if impact_type in counts:
            counts[impact_type] += 1
        try:
            severities.append(int(area.get("severity", 0)))
        except (TypeError, ValueError):
            severities.append(0)

    top = sorted(severities, reverse=True)[:10]
    avg_top = (sum(top) / len(top)) if top else 0
    density = min(len(areas), 26)

    phase_target = 38 + 35 * intensity + 4 * math.sin(progress * math.pi * 2)
    computed = 20 + density * 0.72 + avg_top * 0.38
    overall = int(_clamp(computed * 0.52 + phase_target * 0.30 + original_overall * 0.18, 24, 92))

    city_state["overall_severity"] = overall
    city_state["danger_to_remain"] = _danger_from_severity(overall)
    city_state["operational_status"] = _status_from_severity(overall)

    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    city_state["dominant_impacts"] = [name for name, value in ordered if value > 0][:3]
    city_state["impact_summary"] = {
        "affected_points": len(areas),
        "flooding_points": counts["flooding"],
        "road_closure_points": counts["road_closure"],
        "powerline_failure_points": counts["powerline_failure"],
        "debris_points": counts["debris"],
        "structure_damage_points": counts["structure_damage"],
        "high_wind_points": counts["high_wind"],
    }

    pressure = overall / 100
    city_state["city_services"] = {
        "road_access_ratio": round(_clamp(0.93 - pressure * 0.64, 0.18, 0.97), 2),
        "power_stability_ratio": round(_clamp(0.94 - pressure * 0.62, 0.2, 0.97), 2),
        "drainage_capacity_ratio": round(_clamp(0.9 - pressure * 0.58, 0.16, 0.96), 2),
        "mobility_ratio": round(_clamp(0.9 - pressure * 0.60, 0.18, 0.96), 2),
        "communications_ratio": round(_clamp(0.93 - pressure * 0.52, 0.2, 0.97), 2),
    }

    if overall >= 82:
        city_state["recommended_action"] = (
            "Dynamic rerouting required in affected corridors; prioritize evacuation windows while roads remain passable."
        )
    elif overall >= 68:
        city_state["recommended_action"] = (
            "Use staged detours and monitor flood and wind escalations around route chokepoints."
        )
    else:
        city_state["recommended_action"] = (
            "Maintain readiness and monitor high-wind and flood pockets for rapid change."
        )

    if city_state.get("dominant_impacts"):
        city_state["primary_trigger"] = str(city_state["dominant_impacts"][0]).replace("_", " ")


def augment_city_state_step(raw_step: dict[str, Any], step_index: int, total_steps: int) -> dict[str, Any]:
    """Generate a procedural city-state snapshot with causal hazard progression.

    Chain: high_wind/flooding -> debris/structure_damage -> powerline_failure -> road_closure.
    """
    step = deepcopy(raw_step)
    city_state = step.get("city_state")
    if not isinstance(city_state, dict):
        return step

    raw_areas = city_state.get("affected_areas")
    if not isinstance(raw_areas, list):
        raw_areas = []

    progress = step_index / max(total_steps - 1, 1)
    intensity = _storm_intensity(progress)
    rnd = random.Random(BASE_SEED + step_index * 101)
    forward, lateral = _route_unit_vectors()

    # Keep a few seed anchors as spatial hints only.
    anchors: list[tuple[float, float]] = []
    for item in raw_areas:
        if isinstance(item, dict):
            try:
                anchors.append((float(item["lat"]), float(item["lon"])) )
            except (KeyError, TypeError, ValueError):
                continue

    events: list[dict[str, Any]] = []

    # 1) Base layer: high wind pockets.
    wind_count = 3 + int(3 * intensity)
    for _ in range(wind_count):
        if anchors and rnd.random() < 0.5:
            base_lat, base_lon = rnd.choice(anchors)
            lat, lon = _offset_lat_lon(base_lat, base_lon, rnd.uniform(-700, 700), rnd.uniform(-700, 700))
        else:
            lat, lon = _place_corridor_point(progress, intensity, forward, lateral, rnd, ahead_bias=0.03)
        events.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type="high_wind",
                severity=int(52 + 30 * intensity + rnd.randint(-8, 10)),
                radius_m=int(220 + 260 * intensity + rnd.randint(-40, 90)),
                status=_status_label(progress, rnd),
            )
        )

    # 2) Base layer: flooding from sustained rainfall + runoff.
    flood_count = 2 + int(4 * intensity)
    for _ in range(flood_count):
        lat, lon = _place_corridor_point(progress, intensity, forward, lateral, rnd)
        near_wind = min(
            (
                _distance_m(lat, lon, float(w["lat"]), float(w["lon"]))
                for w in events
                if w["impact_type"] == "high_wind"
            ),
            default=2_000,
        )
        flood_boost = 8 if near_wind < 500 else 0
        events.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type="flooding",
                severity=int(48 + 26 * intensity + flood_boost + rnd.randint(-8, 12)),
                radius_m=int(200 + 320 * intensity + rnd.randint(-30, 120)),
                status=_status_label(progress, rnd),
            )
        )

    floods = [e for e in events if e["impact_type"] == "flooding" and int(e["severity"]) >= 66]
    winds = [e for e in events if e["impact_type"] == "high_wind" and int(e["severity"]) >= 72]

    # 3) Debris/structure damage only when BOTH flood and high wind are severe.
    for flood in floods:
        close_wind = [
            w
            for w in winds
            if _distance_m(float(flood["lat"]), float(flood["lon"]), float(w["lat"]), float(w["lon"])) <= 700
        ]
        if not close_wind:
            continue
        if rnd.random() > 0.58:
            continue

        impact_type = "structure_damage" if rnd.random() < 0.35 else "debris"
        angle = rnd.uniform(0, 2 * math.pi)
        dist = rnd.uniform(120, 380)
        lat, lon = _offset_lat_lon(float(flood["lat"]), float(flood["lon"]), dist * math.cos(angle), dist * math.sin(angle))
        events.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type=impact_type,
                severity=int(int(flood["severity"]) + rnd.randint(-8, 8)),
                radius_m=int(int(flood["radius_m"]) * rnd.uniform(0.65, 1.0)),
                status="new" if rnd.random() < 0.5 else "worsening",
            )
        )

    secondary = [e for e in events if e["impact_type"] in {"debris", "structure_damage"}]

    # 4) Powerline failure requires structural/debris damage (or exceptional wind).
    for src in secondary:
        if rnd.random() > 0.72:
            continue
        angle = rnd.uniform(0, 2 * math.pi)
        dist = rnd.uniform(90, 260)
        lat, lon = _offset_lat_lon(float(src["lat"]), float(src["lon"]), dist * math.cos(angle), dist * math.sin(angle))
        events.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type="powerline_failure",
                severity=int(int(src["severity"]) + rnd.randint(-10, 7)),
                radius_m=int(int(src["radius_m"]) * rnd.uniform(0.62, 0.95)),
                status="worsening",
            )
        )

    # 5) Road closures from high flooding (and optionally debris/structure spillover).
    # These are always high danger and should be rendered with a clear red impact area.
    closure_sources = [e for e in events if e["impact_type"] == "flooding" and int(e["severity"]) >= 76]
    closure_sources.extend([e for e in events if e["impact_type"] in {"debris", "structure_damage"}])
    for src in closure_sources:
        chance = 0.62 if src["impact_type"] == "flooding" else 0.35
        if rnd.random() > chance:
            continue
        angle = rnd.uniform(0, 2 * math.pi)
        dist = rnd.uniform(140, 520)
        lat, lon = _offset_lat_lon(float(src["lat"]), float(src["lon"]), dist * math.cos(angle), dist * math.sin(angle))
        events.append(
            _event(
                lat=lat,
                lon=lon,
                impact_type="road_closure",
                severity=max(70, int(int(src["severity"]) + rnd.randint(-8, 10))),
                radius_m=int(int(src["radius_m"]) * rnd.uniform(0.75, 1.2)),
                status="new" if rnd.random() < 0.4 else "worsening",
            )
        )

    # 6) Merge dense, overlapping low-danger flood/wind pockets into larger cohesive hazards.
    events, merged_floods = _cluster_dense_overlaps(events, impact_type="flooding", min_cluster_size=10)
    events, merged_winds = _cluster_dense_overlaps(events, impact_type="high_wind", min_cluster_size=10)

    # Keep the simulation difficult but solvable.
    events = _ensure_spatial_separation(events, rnd, min_distance_m=95)
    max_events = 16 + int(8 * intensity)
    city_state["affected_areas"] = events[:max_events]

    _recompute_metadata(
        city_state,
        original_overall=int(city_state.get("overall_severity", 0)),
        progress=progress,
        intensity=intensity,
    )

    city_state["note"] = (
        "Procedural causal chain enabled: high wind + flooding create downstream damage, "
        "with occasional route-pressure hazards to force realistic reroutes. "
        f"Cluster merge applied: floods={len(merged_floods)}, winds={len(merged_winds)}."
    )
    step["city_state"] = city_state
    return step


def _procedural_gate_for_route_hazard(city_state: dict[str, Any]) -> bool:
    summary = city_state.get("impact_summary", {}) if isinstance(city_state.get("impact_summary"), dict) else {}
    floods = int(summary.get("flooding_points", 0) or 0)
    winds = int(summary.get("high_wind_points", 0) or 0)
    debris = int(summary.get("debris_points", 0) or 0)
    structures = int(summary.get("structure_damage_points", 0) or 0)
    return floods >= 3 and winds >= 2 and (debris + structures) >= 1


async def maybe_inject_route_hazard(
    augmented_step: dict[str, Any],
    *,
    step_index: int,
    total_steps: int,
) -> None:
    """With low probability, inject a hazard directly on an active route.

    This is deterministic per (route_id, step_index), has a cooldown, and only
    runs when the procedural chain has escalated enough.
    """
    city_state = augmented_step.get("city_state")
    if not isinstance(city_state, dict):
        return
    if not _procedural_gate_for_route_hazard(city_state):
        return

    progress = step_index / max(total_steps - 1, 1)
    if progress < 0.12 or progress > 0.92:
        return

    routes = list(hazard_store._routes.values())
    if not routes:
        return

    for sub in routes:
        route_id = sub.route_id
        key = (route_id, step_index)
        if key in _INJECTED_ROUTE_STEPS:
            continue

        last = _LAST_INJECTED_STEP_BY_ROUTE.get(route_id)
        if last is not None and (step_index - last) < ROUTE_HAZARD_STEP_COOLDOWN:
            continue

        rnd = _seeded_random(route_id, step_index)
        if rnd.random() >= ROUTE_HAZARD_PROBABILITY:
            continue

        # Choose a point near the user's expected progress along the active route.
        frac = _clamp(progress + rnd.uniform(-0.18, 0.16), 0.14, 0.9)
        point = sub.geometry.interpolate(frac, normalized=True)

        hazard_type = "flood" if rnd.random() < 0.6 else "roadblock"
        radius = int(rnd.uniform(120, 240))
        report = HazardReport(
            hazard_type=hazard_type,
            location={"lng": float(point.x), "lat": float(point.y)},
            radius_meters=radius,
            description=f"Procedural route hazard at step {step_index} ({hazard_type})",
        )

        zone = hazard_store.add_hazard(report)
        await hazard_store.notify_affected_routes(zone)

        _INJECTED_ROUTE_STEPS.add(key)
        _LAST_INJECTED_STEP_BY_ROUTE[route_id] = step_index
