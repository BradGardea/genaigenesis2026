from __future__ import annotations

import hashlib
import math
import random
from copy import deepcopy
from typing import Any

from app.models.routing import HazardReport
from app.services.hazard_store import hazard_store

ROUTE_ORIGIN = (-21.910876, 38.412837)  # storm source (lat, lon)
ROUTE_DESTINATION = (-21.972420, 35.274289)  # storm landfall/end (lat, lon)
CITY_CENTER = (-21.941648, 36.843563)
BASE_SEED = 20260314
STORM_WEAKEN_RANGE_M = 160_934  # ~100 miles
SEED_FRONTIER_SIBLINGS = 2
SEED_FRONTIER_SPREAD_M = 800
MAX_COASTAL_SEED_SOURCES = 8
MAX_PROTECTED_FRONTIER_EVENTS = MAX_COASTAL_SEED_SOURCES * (SEED_FRONTIER_SIBLINGS + 1)
SEED_SPAWN_ACTIVE_STEPS = 30
SEED_PROTECTED_STEPS = 30
NODE_INERT_PROBABILITY = 0.20
SEED_CHILD_BASE_PROBABILITY = 0.34
GENERAL_CHILD_BASE_PROBABILITY = 0.24
CHILD_MAX_STEP_DECAY = 0.42
CHILD_SEVERITY_RETENTION_MIN = 0.52
CHILD_SEVERITY_RETENTION_MAX = 0.90
CHILD_RADIUS_RETENTION_MIN = 0.68
CHILD_RADIUS_RETENTION_MAX = 0.96
FLOOD_RAIN_SEVERITY_THRESHOLD = 50
FLOOD_WIND_SEVERITY_THRESHOLD = 54
FLOOD_NEARBY_WIND_DISTANCE_M = 1_800
FLOOD_GENERATION_PROBABILITY = 0.96
FLOOD_SEVERITY_RETENTION = 0.86
SECONDARY_FLOOD_SEVERITY_THRESHOLD = 40
SECONDARY_WIND_SEVERITY_THRESHOLD = 58
SECONDARY_NEARBY_WIND_DISTANCE_M = 1_050
SECONDARY_DAMAGE_PROBABILITY = 0.88
SECONDARY_DAMAGE_SEVERITY_RETENTION = 0.78
POWERLINE_GENERATION_PROBABILITY = 0.55
POWERLINE_SEVERITY_RETENTION = 0.72
ROAD_CLOSURE_FLOOD_THRESHOLD = 68
ROAD_CLOSURE_FROM_FLOOD_PROBABILITY = 0.58
ROAD_CLOSURE_FROM_DAMAGE_PROBABILITY = 0.36
ROAD_CLOSURE_SEVERITY_RETENTION = 0.76
INITIAL_FRONT_OFFSHORE_M = 2600
FRONT_INLAND_ADVANCE_PER_STEP_M = 230
FRONT_INLAND_PROGRESS_BOOST_M = 1100
FRONT_LATERAL_DRIFT_M = 180
OPEN_WATER_FRONT_OFFSET_M = 1100
OPEN_WATER_SPREAD_M = 950
COASTLINE_ANCHORS: list[tuple[float, float]] = [
    (-21.910876, 38.412837),
    (-21.918412, 38.037624),
    (-21.925948, 37.662412),
    (-21.933484, 37.287199),
    (-21.941020, 36.911987),
    (-21.948556, 36.536774),
    (-21.956092, 36.161562),
    (-21.963628, 35.786349),
    (-21.972420, 35.274289),
]

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


def _distance_point_to_segment_m(
    lat: float, lon: float, a_lat: float, a_lon: float, b_lat: float, b_lon: float
) -> float:
    lat_scale = 111_320.0
    lon_scale = 111_320.0 * math.cos(math.radians((a_lat + b_lat + lat) / 3))

    px = lon * lon_scale
    py = lat * lat_scale
    ax = a_lon * lon_scale
    ay = a_lat * lat_scale
    bx = b_lon * lon_scale
    by = b_lat * lat_scale

    abx = bx - ax
    aby = by - ay
    ab2 = abx * abx + aby * aby
    if ab2 <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * abx + (py - ay) * aby) / ab2
    t = _clamp(t, 0.0, 1.0)
    cx = ax + t * abx
    cy = ay + t * aby
    return math.hypot(px - cx, py - cy)


def _is_near_coast(lat: float, lon: float, threshold_m: float = 1_350) -> bool:
    best = float("inf")
    for i in range(len(COASTLINE_ANCHORS) - 1):
        a_lat, a_lon = COASTLINE_ANCHORS[i]
        b_lat, b_lon = COASTLINE_ANCHORS[i + 1]
        d = _distance_point_to_segment_m(lat, lon, a_lat, a_lon, b_lat, b_lon)
        if d < best:
            best = d
    return best <= threshold_m


def _origin_decay_factor(lat: float, lon: float) -> float:
    distance = _distance_m(ROUTE_ORIGIN[0], ROUTE_ORIGIN[1], lat, lon)
    progress = _clamp(distance / STORM_WEAKEN_RANGE_M, 0.0, 1.0)
    # 1.0 near origin, trending toward 0.45 at ~100 miles.
    return 1.0 - 0.55 * progress


def _storm_intensity(progress: float) -> float:
    bell = math.exp(-((progress - 0.58) / 0.27) ** 2)
    pulse = 0.06 * math.sin(progress * math.pi * 4.5)
    return _clamp(0.35 + 0.75 * bell + pulse, 0.28, 1.12)


def _coast_point_and_normals(progress: float) -> tuple[float, float, tuple[float, float], tuple[float, float]]:
    if len(COASTLINE_ANCHORS) < 2:
        lat, lon = COASTLINE_ANCHORS[0]
        return lat, lon, (-1.0, 0.0), (1.0, 0.0)

    clamped = _clamp(progress, 0.0, 1.0)
    scaled = clamped * (len(COASTLINE_ANCHORS) - 1)
    idx = min(int(math.floor(scaled)), len(COASTLINE_ANCHORS) - 2)
    local_t = scaled - idx
    a_lat, a_lon = COASTLINE_ANCHORS[idx]
    b_lat, b_lon = COASTLINE_ANCHORS[idx + 1]
    lat = a_lat + (b_lat - a_lat) * local_t
    lon = a_lon + (b_lon - a_lon) * local_t

    avg_lat = (a_lat + b_lat) / 2
    dx = (b_lon - a_lon) * 111_320.0 * math.cos(math.radians(avg_lat))
    dy = (b_lat - a_lat) * 111_320.0
    mag = math.hypot(dx, dy) or 1.0
    tangent = (dx / mag, dy / mag)
    left = (-tangent[1], tangent[0])
    right = (tangent[1], -tangent[0])
    offshore = left if left[0] < right[0] else right
    inland = (-offshore[0], -offshore[1])
    return lat, lon, offshore, inland


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


def _impact_priority(impact_type: str) -> int:
    priorities = {
        "road_closure": 6,
        "structure_damage": 5,
        "powerline_failure": 4,
        "debris": 4,
        "flooding": 3,
        "high_wind": 2,
        "rain": 1,
    }
    return priorities.get(impact_type, 0)


def _seeded_random(route_id: str, step_index: int) -> random.Random:
    digest = hashlib.sha256(f"{route_id}:{step_index}:{BASE_SEED}".encode("utf-8")).hexdigest()
    seed = int(digest[:16], 16)
    return random.Random(seed)


def _lineage_random(seed_ref: str, step_index: int) -> random.Random:
    digest = hashlib.sha256(f"{seed_ref}:{step_index}:{BASE_SEED}".encode("utf-8")).hexdigest()
    seed = int(digest[:16], 16)
    return random.Random(seed)


def _has_seed_lineage(source_kind: str, source_refs: list[str] | None) -> bool:
    if source_kind.startswith("seed_") or source_kind in {"propagated_seed_drift", "seeded_generated"}:
        return True
    refs = source_refs or []
    return any(str(ref).startswith("seed:") for ref in refs)


def _event_lineage_key(area: dict[str, Any]) -> str:
    refs = [str(ref) for ref in area.get("source_refs", []) if str(ref)]
    if refs:
        return "|".join(sorted(refs))
    node_id = str(area.get("node_id", ""))
    if node_id:
        return node_id
    return f"{area.get('impact_type', 'other')}:{area.get('lat', 0)}:{area.get('lon', 0)}"


def _event_step_random(area: dict[str, Any], step_index: int, salt: str) -> random.Random:
    digest = hashlib.sha256(
        f"{_event_lineage_key(area)}:{step_index}:{salt}:{BASE_SEED}".encode("utf-8")
    ).hexdigest()
    return random.Random(int(digest[:16], 16))


def _seed_refs(area: dict[str, Any]) -> set[str]:
    return {str(ref) for ref in area.get("source_refs", []) if str(ref).startswith("seed:")}


def _shares_seed_lineage(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(_seed_refs(left) & _seed_refs(right))


def _child_decay(progress: float, intensity: float, *, seed_lineage: bool) -> float:
    fade = 1.0 - CHILD_MAX_STEP_DECAY * progress
    if seed_lineage:
        fade += 0.06
    fade -= max(0.0, intensity - 0.85) * 0.08
    return _clamp(fade, CHILD_SEVERITY_RETENTION_MIN, CHILD_SEVERITY_RETENTION_MAX)


def _child_radius_decay(progress: float, intensity: float) -> float:
    fade = 1.0 - (CHILD_MAX_STEP_DECAY * 0.55) * progress + max(0.0, intensity - 0.75) * 0.05
    return _clamp(fade, CHILD_RADIUS_RETENTION_MIN, CHILD_RADIUS_RETENTION_MAX)


def _drift_seed_inland(
    *,
    seed_ref: str,
    lat: float,
    lon: float,
    step_index: int,
    progress: float,
    intensity: float,
) -> tuple[float, float]:
    """Advect coastal seed anchors inland over time instead of pinning them to the coast."""
    rnd = _lineage_random(seed_ref, step_index)
    coastal_progress = 0.0
    for idx, (_lat, _lon) in enumerate(COASTLINE_ANCHORS):
        if abs(_lat - lat) < 0.02 and abs(_lon - lon) < 0.02:
            coastal_progress = idx / max(len(COASTLINE_ANCHORS) - 1, 1)
            break
    _, _, offshore, inland = _coast_point_and_normals(coastal_progress)
    inland_distance_m = (
        -INITIAL_FRONT_OFFSHORE_M
        + step_index * FRONT_INLAND_ADVANCE_PER_STEP_M
        + progress * FRONT_INLAND_PROGRESS_BOOST_M
    )
    lateral_angle = math.atan2(inland[1], inland[0]) + math.pi / 2
    lateral_distance_m = rnd.uniform(-FRONT_LATERAL_DRIFT_M, FRONT_LATERAL_DRIFT_M) * (0.55 + 0.45 * intensity)
    return _offset_lat_lon(
        lat,
        lon,
        inland_distance_m * inland[0] + lateral_distance_m * math.cos(lateral_angle),
        inland_distance_m * inland[1] + lateral_distance_m * math.sin(lateral_angle),
    )


def _select_evenly_spaced_seeds(
    seeds: list[tuple[str, dict[str, Any]]], max_items: int
) -> list[tuple[str, dict[str, Any]]]:
    if len(seeds) <= max_items:
        return seeds
    selected: list[tuple[str, dict[str, Any]]] = []
    for idx in range(max_items):
        pos = round(idx * (len(seeds) - 1) / max(max_items - 1, 1))
        selected.append(seeds[pos])
    return selected


def _event(
    *,
    lat: float,
    lon: float,
    impact_type: str,
    severity: int,
    radius_m: int,
    status: str,
    source_kind: str = "generated",
    source_refs: list[str] | None = None,
    node_id: str | None = None,
) -> dict[str, Any]:
    sev = int(_clamp(severity, 5, 100))
    return {
        "node_id": node_id,
        "lat": lat,
        "lon": lon,
        "impact_type": impact_type,
        "severity": sev,
        "danger_to_remain": _danger_from_severity(sev),
        "status": status,
        "radius_m": int(_clamp(radius_m, 50, 1800)),
        "source_kind": source_kind,
        "source_refs": source_refs or [],
    }


def _is_low_danger(area: dict[str, Any]) -> bool:
    danger = str(area.get("danger_to_remain", "low")).lower()
    return danger not in {"high", "extreme"}


def _is_protected_seed(area: dict[str, Any]) -> bool:
    return str(area.get("source_kind", "")).endswith("_protected")


def _cluster_dense_overlaps(
    events: list[dict[str, Any]],
    *,
    impact_type: str,
    min_cluster_size: int = 6,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    protected = [e for e in events if _is_protected_seed(e)]
    candidates = [
        e
        for e in events
        if e.get("impact_type") == impact_type and _is_low_danger(e) and not _is_protected_seed(e)
    ]
    if len(candidates) < min_cluster_size:
        return events, []

    adjacency: dict[int, set[int]] = {i: set() for i in range(len(candidates))}
    for i in range(len(candidates)):
        a = candidates[i]
        for j in range(i + 1, len(candidates)):
            b = candidates[j]
            d = _distance_m(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]))
            overlap_threshold = 0.85 * (float(a["radius_m"]) + float(b["radius_m"]))
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

        refs = []
        for g in group:
            refs.extend([str(r) for r in g.get("source_refs", [])])
            node = g.get("node_id")
            if node:
                refs.append(str(node))
        refs = sorted(set(refs))[:16]

        radius_cap = 1200 if impact_type in {"flooding", "high_wind", "rain"} else 1700
        merged_events.append(
            _event(
                lat=center_lat,
                lon=center_lon,
                impact_type=impact_type,
                severity=int(_clamp(max_severity + 6, 42, 86)),
                radius_m=int(_clamp(max_radius + math.sqrt(len(group)) * 95, 220, radius_cap)),
                status="merged_cluster",
                source_kind="merged_cluster",
                source_refs=refs,
                node_id=f"merge-{impact_type}-{abs(int(center_lat*1e6))}-{abs(int(center_lon*1e6))}",
            )
        )

    kept = [e for e in events if id(e) not in to_remove_ids]
    kept.extend(protected)
    kept.extend(merged_events)
    return kept, merged_events


def _place_front_band_point(
    rnd: random.Random,
    intensity: float,
    progress: float,
    *,
    offshore_bias_m: float = 0.0,
    along_bias: float = 0.0,
) -> tuple[float, float]:
    anchor_progress = _clamp(rnd.uniform(0.02, 0.98) + along_bias, 0.0, 1.0)
    base_lat, base_lon, offshore, inland = _coast_point_and_normals(anchor_progress)
    offshore_m = (
        OPEN_WATER_FRONT_OFFSET_M
        + rnd.uniform(-OPEN_WATER_SPREAD_M, OPEN_WATER_SPREAD_M) * (0.75 + 0.35 * intensity)
        + offshore_bias_m
        - progress * (FRONT_INLAND_ADVANCE_PER_STEP_M * 0.45)
    )
    along_angle = math.atan2(inland[1], inland[0]) + math.pi / 2
    along_m = rnd.uniform(-900, 900) * (0.7 + 0.35 * intensity)
    return _offset_lat_lon(
        base_lat,
        base_lon,
        offshore_m * offshore[0] + along_m * math.cos(along_angle),
        offshore_m * offshore[1] + along_m * math.sin(along_angle),
    )


def _place_open_water_front_point(rnd: random.Random, intensity: float, progress: float) -> tuple[float, float]:
    return _place_front_band_point(
        rnd,
        intensity,
        progress,
        offshore_bias_m=rnd.uniform(350, 1100),
        along_bias=rnd.uniform(-0.06, 0.06),
    )


def _place_outer_front_point(rnd: random.Random, intensity: float, progress: float) -> tuple[float, float]:
    return _place_front_band_point(
        rnd,
        intensity,
        progress,
        offshore_bias_m=rnd.uniform(900, 1800),
        along_bias=rnd.uniform(-0.12, 0.12),
    )


def _compress_into_high_danger(events: list[dict[str, Any]], impact_type: str) -> list[dict[str, Any]]:
    highs = [
        e
        for e in events
        if e.get("impact_type") == impact_type and str(e.get("danger_to_remain", "")).lower() in {"high", "extreme"}
    ]
    if not highs:
        return events

    lows = [
        e
        for e in events
        if e.get("impact_type") == impact_type
        and str(e.get("danger_to_remain", "")).lower() not in {"high", "extreme"}
        and not _is_protected_seed(e)
    ]
    absorbed_ids: set[int] = set()
    for high in highs:
        center_lat = float(high["lat"])
        center_lon = float(high["lon"])
        radius_m = float(high["radius_m"])
        absorbed = 0
        for low in lows:
            low_id = id(low)
            if low_id in absorbed_ids:
                continue
            if _distance_m(center_lat, center_lon, float(low["lat"]), float(low["lon"])) <= radius_m:
                absorbed_ids.add(low_id)
                absorbed += 1
        if absorbed > 0:
            high["radius_m"] = int(_clamp(radius_m + math.sqrt(absorbed) * 70, 100, 1800))
            high["severity"] = int(_clamp(int(high["severity"]) + min(absorbed, 8), 5, 100))
            high["danger_to_remain"] = _danger_from_severity(int(high["severity"]))
            high["status"] = "merged_cluster"

    return [e for e in events if id(e) not in absorbed_ids]


def _collapse_nearby_nodes(events: list[dict[str, Any]], merge_distance_m: float = 220) -> list[dict[str, Any]]:
    protected = [e for e in events if _is_protected_seed(e)]
    mutable_events = [e for e in events if not _is_protected_seed(e)]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in mutable_events:
        danger = str(event.get("danger_to_remain", "low")).lower()
        bucket = "high" if danger in {"high", "extreme"} else "low"
        key = (str(event.get("impact_type", "other")), bucket)
        grouped.setdefault(key, []).append(event)

    collapsed: list[dict[str, Any]] = []
    for (impact_type, _bucket), group in grouped.items():
        remaining = group[:]
        while remaining:
            seed = remaining.pop()
            cluster = [seed]
            changed = True
            while changed:
                changed = False
                keep: list[dict[str, Any]] = []
                for item in remaining:
                    if any(
                        _distance_m(float(item["lat"]), float(item["lon"]), float(c["lat"]), float(c["lon"]))
                        <= merge_distance_m
                        for c in cluster
                    ):
                        cluster.append(item)
                        changed = True
                    else:
                        keep.append(item)
                remaining = keep

            if len(cluster) == 1:
                collapsed.append(cluster[0])
                continue

            total_weight = sum(max(float(c["radius_m"]), 1.0) for c in cluster)
            center_lat = sum(float(c["lat"]) * max(float(c["radius_m"]), 1.0) for c in cluster) / total_weight
            center_lon = sum(float(c["lon"]) * max(float(c["radius_m"]), 1.0) for c in cluster) / total_weight
            max_radius = max(float(c["radius_m"]) for c in cluster)
            max_severity = max(int(c["severity"]) for c in cluster)
            radius_cap = 1200 if impact_type in {"flooding", "high_wind", "rain"} else 1800
            refs = []
            for c in cluster:
                refs.extend([str(r) for r in c.get("source_refs", [])])
                node = c.get("node_id")
                if node:
                    refs.append(str(node))
            refs = sorted(set(refs))[:20]
            collapsed.append(
                _event(
                    lat=center_lat,
                    lon=center_lon,
                    impact_type=impact_type,
                    severity=int(_clamp(max_severity + min(6, len(cluster)), 12, 100)),
                    radius_m=int(_clamp(max_radius + math.sqrt(len(cluster)) * 85, 90, radius_cap)),
                    status="merged_cluster",
                    source_kind="collapsed_cluster",
                    source_refs=refs,
                    node_id=f"collapse-{impact_type}-{abs(int(center_lat*1e6))}-{abs(int(center_lon*1e6))}",
                )
            )

    collapsed.extend(protected)
    return collapsed


def _ensure_spatial_separation(
    areas: list[dict[str, Any]], rnd: random.Random, min_distance_m: float = 90
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    for area in areas:
        if _is_protected_seed(area):
            accepted.append(area)
            continue
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
        "rain": 0,
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
        "rain_points": counts["rain"],
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

    # Keep a few seed anchors as spatial hints only.
    anchors: list[tuple[str, float, float]] = []
    coastal_seed_nodes: list[tuple[str, dict[str, Any]]] = []
    for idx, item in enumerate(raw_areas):
        if isinstance(item, dict):
            try:
                lat = float(item["lat"])
                lon = float(item["lon"])
                seed_ref = f"seed:{idx}"
                impact = str(item.get("impact_type", ""))
                if impact in {"rain", "high_wind"} and _is_near_coast(lat, lon):
                    drift_lat, drift_lon = _drift_seed_inland(
                        seed_ref=seed_ref,
                        lat=lat,
                        lon=lon,
                        step_index=step_index,
                        progress=progress,
                        intensity=intensity,
                    )
                    anchors.append((seed_ref, drift_lat, drift_lon))
                    coastal_seed_nodes.append((seed_ref, item))
                else:
                    anchors.append((seed_ref, lat, lon))
            except (KeyError, TypeError, ValueError):
                continue
    coastal_seed_nodes = _select_evenly_spaced_seeds(coastal_seed_nodes, MAX_COASTAL_SEED_SOURCES)

    events: list[dict[str, Any]] = []
    event_seq = 0

    def emit_event(
        *,
        lat: float,
        lon: float,
        impact_type: str,
        severity: int,
        radius_m: int,
        status: str,
        source_kind: str = "generated",
        source_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        nonlocal event_seq
        event_seq += 1
        return _event(
            lat=lat,
            lon=lon,
            impact_type=impact_type,
            severity=severity,
            radius_m=radius_m,
            status=status,
            source_kind=source_kind,
            source_refs=source_refs,
            node_id=f"step{step_index}-n{event_seq}",
        )

    preserve_coast_seeds = step_index <= SEED_PROTECTED_STEPS
    for seed_ref, raw_seed in coastal_seed_nodes:
        lat = float(raw_seed.get("lat", ROUTE_ORIGIN[0]))
        lon = float(raw_seed.get("lon", ROUTE_ORIGIN[1]))
        drift_lat, drift_lon = _drift_seed_inland(
            seed_ref=seed_ref,
            lat=lat,
            lon=lon,
            step_index=step_index,
            progress=progress,
            intensity=intensity,
        )
        severity = int(raw_seed.get("severity", 50))
        radius = int(raw_seed.get("radius_m", 180))
        impact_type = str(raw_seed.get("impact_type", "rain"))
        drift_rnd = _lineage_random(seed_ref, step_index)
        frontier_angle = drift_rnd.normalvariate(2.20, 0.14)
        frontier_offsets = [0.0]
        for sibling_index in range(SEED_FRONTIER_SIBLINGS):
            direction = -1 if sibling_index % 2 == 0 else 1
            frontier_offsets.append(direction * (sibling_index // 2 + 1) * SEED_FRONTIER_SPREAD_M)

        for offset_index, frontier_offset in enumerate(frontier_offsets):
            seed_lat, seed_lon = _offset_lat_lon(
                drift_lat,
                drift_lon,
                frontier_offset * math.cos(frontier_angle),
                frontier_offset * math.sin(frontier_angle),
            )
            sibling_severity = severity * (1.0 - min(abs(frontier_offset) / max(SEED_FRONTIER_SPREAD_M, 1), 2.0) * 0.08)
            sibling_radius = radius * (1.0 - min(abs(frontier_offset) / max(SEED_FRONTIER_SPREAD_M, 1), 2.0) * 0.06)
            source_kind = "seed_coast_protected" if offset_index == 0 and preserve_coast_seeds else "seed_coast"
            if offset_index > 0:
                source_kind = "seed_frontier_protected" if preserve_coast_seeds else "seed_frontier"
            events.append(
                emit_event(
                    lat=seed_lat,
                    lon=seed_lon,
                    impact_type=impact_type,
                    severity=int(_clamp(sibling_severity, 26, 76)),
                    radius_m=int(_clamp(sibling_radius, 100, 460)),
                    status=str(raw_seed.get("status", "persistent")),
                    source_kind=source_kind,
                    source_refs=[seed_ref, f"frontier:{offset_index}"] if offset_index > 0 else [seed_ref],
                )
            )

    # Explicit seed drift: children from coastal seeds move north/northeast over time.
    for event in [e for e in events if str(e.get("source_kind", "")).startswith("seed_")]:
        if step_index > SEED_SPAWN_ACTIVE_STEPS:
            continue
        if _event_step_random(event, step_index, "seed-inert").random() < NODE_INERT_PROBABILITY:
            continue
        if rnd.random() > min(0.95, SEED_CHILD_BASE_PROBABILITY + 0.20 * intensity):
            continue
        mean_angle = 1.00 + 0.24 * progress  # NE -> NNE
        angle = rnd.normalvariate(mean_angle, 0.20)
        dist = rnd.uniform(240, 980)
        lat, lon = _offset_lat_lon(float(event["lat"]), float(event["lon"]), dist * math.cos(angle), dist * math.sin(angle))
        decay = _origin_decay_factor(lat, lon)
        child_decay = _child_decay(progress, intensity, seed_lineage=True)
        radius_decay = _child_radius_decay(progress, intensity)
        events.append(
            emit_event(
                lat=lat,
                lon=lon,
                impact_type=str(event["impact_type"]),
                severity=int(int(event["severity"]) * rnd.uniform(0.84, 0.98) * child_decay * decay),
                radius_m=int(int(event["radius_m"]) * rnd.uniform(0.84, 0.98) * radius_decay),
                status="worsening",
                source_kind="propagated_seed_drift",
                source_refs=[str(event.get("node_id", ""))]
                + [str(ref) for ref in event.get("source_refs", []) if str(ref)],
            )
        )

    # 1) Base layer: high wind pockets.
    wind_count = 3 + int(2 * intensity)
    for _ in range(wind_count):
        selector = rnd.random()
        if selector < 0.30:
            lat, lon = _place_open_water_front_point(rnd, intensity, progress)
            refs: list[str] = ["placement:front_open_water"]
            source_kind = "generated_front_open_water"
        elif selector < 0.58:
            lat, lon = _place_outer_front_point(rnd, intensity, progress)
            refs = ["placement:front_outer"]
            source_kind = "generated_front_outer"
        elif anchors and rnd.random() < 0.42:
            seed_ref, base_lat, base_lon = rnd.choice(anchors)
            anchor_rnd = _lineage_random(seed_ref, step_index)
            lat, lon = _offset_lat_lon(
                base_lat,
                base_lon,
                anchor_rnd.uniform(-360, 520),
                anchor_rnd.uniform(90, 760),
            )
            refs = [seed_ref]
            source_kind = "seeded_generated"
        else:
            lat, lon = _place_front_band_point(rnd, intensity, progress, offshore_bias_m=rnd.uniform(-180, 380))
            refs = ["placement:front_band"]
            source_kind = "generated_front_band"
        decay = _origin_decay_factor(lat, lon)
        events.append(
            emit_event(
                lat=lat,
                lon=lon,
                impact_type="high_wind",
                severity=int((50 + 22 * intensity + rnd.randint(-8, 8)) * decay),
                radius_m=int((180 + 210 * intensity + rnd.randint(-35, 85)) * (0.9 + 0.2 * decay)),
                status=_status_label(progress, rnd),
                source_kind=source_kind,
                source_refs=refs,
            )
        )

    # 2) Base layer: rain pockets (precursor to flooding).
    rain_count = 3 + int(3 * intensity)
    for _ in range(rain_count):
        selector = rnd.random()
        if selector < 0.28:
            lat, lon = _place_open_water_front_point(rnd, intensity, progress)
            refs = ["placement:front_open_water"]
            source_kind = "generated_front_open_water"
        elif selector < 0.52:
            lat, lon = _place_outer_front_point(rnd, intensity, progress)
            refs = ["placement:front_outer"]
            source_kind = "generated_front_outer"
        else:
            lat, lon = _place_front_band_point(rnd, intensity, progress, offshore_bias_m=rnd.uniform(-260, 320))
            refs = ["placement:front_band"]
            source_kind = "generated_front_band"
        decay = _origin_decay_factor(lat, lon)
        events.append(
            emit_event(
                lat=lat,
                lon=lon,
                impact_type="rain",
                severity=int((52 + 20 * intensity + rnd.randint(-9, 10)) * decay),
                radius_m=int((170 + 230 * intensity + rnd.randint(-25, 90)) * (0.9 + 0.2 * decay)),
                status=_status_label(progress, rnd),
                source_kind=source_kind,
                source_refs=refs,
            )
        )

    # Natural progression: strong rain/wind nodes can spawn nearby child cells
    # regardless of user position, reducing path-centric bias.
    propagation_sources = [
        e for e in events if e["impact_type"] in {"rain", "high_wind"} and int(e["severity"]) >= 58
    ]
    for src in propagation_sources:
        step_rnd = _event_step_random(src, step_index, "child-propagation")
        if step_rnd.random() < NODE_INERT_PROBABILITY:
            continue
        seed_lineage = _has_seed_lineage(str(src.get("source_kind", "")), [str(r) for r in src.get("source_refs", [])])
        child_probability = SEED_CHILD_BASE_PROBABILITY if seed_lineage else GENERAL_CHILD_BASE_PROBABILITY
        if rnd.random() > min(0.94, child_probability + 0.30 * intensity):
            continue
        source_kind = str(src.get("source_kind", ""))
        source_refs = [str(r) for r in src.get("source_refs", [])]
        if seed_lineage:
            # Make seeded coastal growth drift north/northeast over time.
            mean_angle = 1.02 + 0.22 * progress  # ~58deg to ~71deg from east axis
            angle = rnd.normalvariate(mean_angle, 0.22)
            dist = rnd.uniform(260, 1120)
        else:
            angle = rnd.uniform(0, 2 * math.pi)
            dist = rnd.uniform(180, 820)
        lat, lon = _offset_lat_lon(float(src["lat"]), float(src["lon"]), dist * math.cos(angle), dist * math.sin(angle))
        decay = _origin_decay_factor(lat, lon)
        child_decay = _child_decay(progress, intensity, seed_lineage=seed_lineage)
        radius_decay = _child_radius_decay(progress, intensity)
        refs = [str(src.get("node_id", ""))] + source_refs
        events.append(
            emit_event(
                lat=lat,
                lon=lon,
                impact_type=str(src["impact_type"]),
                severity=int(int(src["severity"]) * rnd.uniform(0.82, 0.96) * child_decay * decay),
                radius_m=int(int(src["radius_m"]) * rnd.uniform(0.80, 0.96) * radius_decay),
                status="worsening",
                source_kind="propagated",
                source_refs=[r for r in refs if r],
            )
        )

    rains = [e for e in events if e["impact_type"] == "rain" and int(e["severity"]) >= FLOOD_RAIN_SEVERITY_THRESHOLD]
    winds = [e for e in events if e["impact_type"] == "high_wind" and int(e["severity"]) >= FLOOD_WIND_SEVERITY_THRESHOLD]

    # 3) Flooding emerges from co-located rain + wind.
    for rain in rains:
        nearby_wind = [
            w
            for w in winds
            if _distance_m(float(rain["lat"]), float(rain["lon"]), float(w["lat"]), float(w["lon"]))
            <= FLOOD_NEARBY_WIND_DISTANCE_M
        ]
        if not nearby_wind:
            continue
        if _event_step_random(rain, step_index, "flood-inert").random() < NODE_INERT_PROBABILITY * 0.5:
            continue
        shared_lineage = any(_shares_seed_lineage(rain, wind) for wind in nearby_wind)
        flood_probability = min(0.995, FLOOD_GENERATION_PROBABILITY + (0.03 if shared_lineage else 0.0))
        if rnd.random() > flood_probability:
            continue
        mean_wind_sev = sum(int(w["severity"]) for w in nearby_wind) / len(nearby_wind)
        strongest_wind = max(nearby_wind, key=lambda wind: int(wind["severity"]))
        lat = (float(rain["lat"]) + float(strongest_wind["lat"])) / 2
        lon = (float(rain["lon"]) + float(strongest_wind["lon"])) / 2
        decay = _origin_decay_factor(lat, lon)
        flood_sev = int(
            (0.52 * int(rain["severity"]) + 0.42 * mean_wind_sev + rnd.randint(-4, 8))
            * FLOOD_SEVERITY_RETENTION
            * _child_decay(progress, intensity, seed_lineage=_has_seed_lineage(str(rain.get("source_kind", "")), [str(r) for r in rain.get("source_refs", [])]))
            * decay
        )
        refs = [str(rain.get("node_id", ""))] + [str(w.get("node_id", "")) for w in nearby_wind[:3]]
        events.append(
            emit_event(
                lat=lat,
                lon=lon,
                impact_type="flooding",
                severity=flood_sev,
                radius_m=int(int(rain["radius_m"]) * rnd.uniform(0.85, 1.25)),
                status="new" if rnd.random() < 0.5 else "worsening",
                source_kind="derived_flood_from_rain_wind",
                source_refs=[r for r in refs if r],
            )
        )

    floods = [e for e in events if e["impact_type"] == "flooding" and int(e["severity"]) >= SECONDARY_FLOOD_SEVERITY_THRESHOLD]

    # 4) Debris/structure damage only when BOTH flood and high wind are severe.
    for flood in floods:
        close_wind = [
            w
            for w in winds
            if _distance_m(float(flood["lat"]), float(flood["lon"]), float(w["lat"]), float(w["lon"]))
            <= SECONDARY_NEARBY_WIND_DISTANCE_M
            and int(w["severity"]) >= SECONDARY_WIND_SEVERITY_THRESHOLD
        ]
        if not close_wind and int(flood["severity"]) < 50:
            continue
        if _event_step_random(flood, step_index, "secondary-inert").random() < NODE_INERT_PROBABILITY * 0.5:
            continue
        secondary_probability = SECONDARY_DAMAGE_PROBABILITY if close_wind else max(0.72, SECONDARY_DAMAGE_PROBABILITY - 0.10)
        if rnd.random() > secondary_probability:
            continue

        impact_type = "structure_damage" if close_wind and rnd.random() < 0.42 else "debris"
        angle = rnd.uniform(0, 2 * math.pi)
        dist = rnd.uniform(120, 380)
        lat, lon = _offset_lat_lon(float(flood["lat"]), float(flood["lon"]), dist * math.cos(angle), dist * math.sin(angle))
        refs = [str(flood.get("node_id", ""))] + [str(w.get("node_id", "")) for w in close_wind[:2]]
        wind_pressure = sum(int(w["severity"]) for w in close_wind[:2]) if close_wind else int(flood["severity"]) * 0.55
        events.append(
            emit_event(
                lat=lat,
                lon=lon,
                impact_type=impact_type,
                severity=int(
                    (int(flood["severity"]) + 0.22 * wind_pressure + rnd.randint(-6, 8))
                    * SECONDARY_DAMAGE_SEVERITY_RETENTION
                    * _child_decay(progress, intensity, seed_lineage=False)
                ),
                radius_m=int(int(flood["radius_m"]) * rnd.uniform(0.60, 0.92) * _child_radius_decay(progress, intensity)),
                status="new" if rnd.random() < 0.5 else "worsening",
                source_kind="derived_damage",
                source_refs=[r for r in refs if r],
            )
        )

    secondary = [e for e in events if e["impact_type"] in {"debris", "structure_damage"}]

    # 5) Powerline failure requires structural/debris damage.
    for src in secondary:
        if _event_step_random(src, step_index, "powerline-inert").random() < NODE_INERT_PROBABILITY * 0.5:
            continue
        if rnd.random() > POWERLINE_GENERATION_PROBABILITY:
            continue
        angle = rnd.uniform(0, 2 * math.pi)
        dist = rnd.uniform(90, 260)
        lat, lon = _offset_lat_lon(float(src["lat"]), float(src["lon"]), dist * math.cos(angle), dist * math.sin(angle))
        refs = [str(src.get("node_id", ""))] + [str(r) for r in src.get("source_refs", [])]
        events.append(
            emit_event(
                lat=lat,
                lon=lon,
                impact_type="powerline_failure",
                severity=int(
                    (int(src["severity"]) + rnd.randint(-8, 6))
                    * POWERLINE_SEVERITY_RETENTION
                    * _child_decay(progress, intensity, seed_lineage=False)
                ),
                radius_m=int(int(src["radius_m"]) * rnd.uniform(0.58, 0.88) * _child_radius_decay(progress, intensity)),
                status="worsening",
                source_kind="derived_powerline",
                source_refs=[r for r in refs if r],
            )
        )

    # 6) Road closures from high flooding (and optionally debris/structure spillover).
    # These are always high danger and should be rendered with a clear red impact area.
    closure_sources = [e for e in events if e["impact_type"] == "flooding" and int(e["severity"]) >= ROAD_CLOSURE_FLOOD_THRESHOLD]
    closure_sources.extend([e for e in events if e["impact_type"] in {"debris", "structure_damage"}])
    for src in closure_sources:
        chance = ROAD_CLOSURE_FROM_FLOOD_PROBABILITY if src["impact_type"] == "flooding" else ROAD_CLOSURE_FROM_DAMAGE_PROBABILITY
        if rnd.random() > chance:
            continue
        angle = rnd.uniform(0, 2 * math.pi)
        dist = rnd.uniform(140, 520)
        lat, lon = _offset_lat_lon(float(src["lat"]), float(src["lon"]), dist * math.cos(angle), dist * math.sin(angle))
        refs = [str(src.get("node_id", ""))] + [str(r) for r in src.get("source_refs", [])]
        events.append(
            emit_event(
                lat=lat,
                lon=lon,
                impact_type="road_closure",
                severity=max(
                    70,
                    int(
                        (int(src["severity"]) + rnd.randint(-6, 8))
                        * ROAD_CLOSURE_SEVERITY_RETENTION
                        * _child_decay(progress, intensity, seed_lineage=False)
                    ),
                ),
                radius_m=int(int(src["radius_m"]) * rnd.uniform(0.70, 1.05) * _child_radius_decay(progress, intensity)),
                status="new" if rnd.random() < 0.4 else "worsening",
                source_kind="derived_road_closure",
                source_refs=[r for r in refs if r],
            )
        )

    events = _compress_into_high_danger(events, "flooding")
    events = _compress_into_high_danger(events, "high_wind")
    events = _compress_into_high_danger(events, "rain")
    events = _compress_into_high_danger(events, "road_closure")

    # 7) Merge dense, overlapping low-danger flood/wind pockets into larger cohesive hazards.
    events, merged_floods = _cluster_dense_overlaps(events, impact_type="flooding", min_cluster_size=6)
    events, merged_winds = _cluster_dense_overlaps(events, impact_type="high_wind", min_cluster_size=6)

    # Keep the simulation difficult but solvable.
    events = _collapse_nearby_nodes(events, merge_distance_m=240)
    events = _ensure_spatial_separation(events, rnd, min_distance_m=95)
    max_events = 12 + int(5 * intensity)
    if preserve_coast_seeds:
        protected = [e for e in events if _is_protected_seed(e)][:MAX_PROTECTED_FRONTIER_EVENTS]
        others = [e for e in events if not _is_protected_seed(e)]
        others.sort(key=lambda event: (_impact_priority(str(event.get("impact_type", ""))), int(event.get("severity", 0))), reverse=True)
        city_state["affected_areas"] = protected + others[:max_events]
    else:
        events.sort(key=lambda event: (_impact_priority(str(event.get("impact_type", ""))), int(event.get("severity", 0))), reverse=True)
        city_state["affected_areas"] = events[:max_events]

    _recompute_metadata(
        city_state,
        original_overall=int(city_state.get("overall_severity", 0)),
        progress=progress,
        intensity=intensity,
    )

    city_state["note"] = (
        "Procedural causal chain enabled: rain + high wind create flooding and downstream damage, "
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
