#!/usr/bin/env python3
"""
transform_storm.py

Scale a synthetic storm dataset spatially and/or move it so the first storm
center starts at a user-specified coordinate.

What gets scaled:
- storm_state.radius_of_maximum_wind_km
- storm_state.wind_radii_km.{r34,r50,r64}
- storm_state.forecast_cone_km
- storm_state.focus_points (scaled radially around the storm center)
- storm_state.forecast_next.*.center_range_km
- storm_state.forecast_next.*.wind_radii_km.{r34,r50,r64}

What gets moved when a target start coordinate is provided:
- storm_state.storm_center
- storm_state.focus_points
- storm_state.forecast_next.*.storm_center

Optional:
- move root location latitude/longitude
- move prediction_summary latitude/longitude and nested hazard lat/lon

Notes:
- This treats local lat/lon offsets as approximately linear, which is fine for
  synthetic/local scenarios like this.
- Weather intensity values (wind speed, rainfall, humidity, etc.) are NOT changed.
"""

from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def round_int(value: float) -> int:
    """Round to nearest int with a floor at 0."""
    return max(0, int(round(value)))


def round_float(value: float, digits: int = 4) -> float:
    """Round float to a fixed number of digits."""
    return round(value, digits)


def scale_scalar(value: Any, factor: float, as_int: bool = False, digits: int = 4) -> Any:
    """Scale a numeric scalar if possible."""
    if not isinstance(value, (int, float)):
        return value
    scaled = value * factor
    return round_int(scaled) if as_int else round_float(scaled, digits)


def scale_range(value: Any, factor: float, as_int: bool = False, digits: int = 4) -> Any:
    """Scale a [low, high] range if present."""
    if (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(x, (int, float)) for x in value)
    ):
        if as_int:
            return [round_int(value[0] * factor), round_int(value[1] * factor)]
        return [round_float(value[0] * factor, digits), round_float(value[1] * factor, digits)]
    return value


def shift_point(point: Dict[str, Any], dlat: float, dlon: float) -> None:
    """Shift a point in-place if it has lat/lon."""
    if "lat" in point and "lon" in point:
        point["lat"] = round_float(point["lat"] + dlat, 5)
        point["lon"] = round_float(point["lon"] + dlon, 5)


def shift_latlon_fields(obj: Dict[str, Any], lat_key: str, lon_key: str, dlat: float, dlon: float) -> None:
    """Shift custom latitude/longitude key pairs in-place."""
    if lat_key in obj and lon_key in obj:
        obj[lat_key] = round_float(obj[lat_key] + dlat, 5)
        obj[lon_key] = round_float(obj[lon_key] + dlon, 5)


def scale_point_around_center(
    point: Dict[str, Any],
    center: Dict[str, Any],
    factor: float
) -> None:
    """
    Scale a point radially around a given center.
    Only affects local spatial footprint, not track translation.
    """
    if not ("lat" in point and "lon" in point and "lat" in center and "lon" in center):
        return

    dlat = point["lat"] - center["lat"]
    dlon = point["lon"] - center["lon"]

    point["lat"] = round_float(center["lat"] + dlat * factor, 5)
    point["lon"] = round_float(center["lon"] + dlon * factor, 5)


def compute_translation(data: Dict[str, Any], target_lat: float, target_lon: float) -> Tuple[float, float]:
    """Compute delta needed so the first storm center starts at target lat/lon."""
    timesteps = data.get("timesteps", [])
    if not timesteps:
        raise ValueError("Dataset has no timesteps.")

    first_center = timesteps[0].get("storm_state", {}).get("storm_center")
    if not first_center or "lat" not in first_center or "lon" not in first_center:
        raise ValueError("Could not find first timestep storm_state.storm_center.")

    dlat = target_lat - first_center["lat"]
    dlon = target_lon - first_center["lon"]
    return dlat, dlon


def scale_storm_state(storm_state: Dict[str, Any], scale: float) -> None:
    """Scale the spatial footprint of a single storm_state."""
    center = storm_state.get("storm_center", {})

    # Scale primary footprint
    if "radius_of_maximum_wind_km" in storm_state:
        storm_state["radius_of_maximum_wind_km"] = scale_scalar(
            storm_state["radius_of_maximum_wind_km"], scale, as_int=True
        )

    if "forecast_cone_km" in storm_state:
        storm_state["forecast_cone_km"] = scale_scalar(
            storm_state["forecast_cone_km"], scale, as_int=True
        )

    # Scale current wind radii
    wind_radii = storm_state.get("wind_radii_km")
    if isinstance(wind_radii, dict):
        for key in ("r34", "r50", "r64"):
            if key in wind_radii:
                wind_radii[key] = scale_scalar(wind_radii[key], scale, as_int=True)

    # Scale focus points radially around current center
    focus_points = storm_state.get("focus_points")
    if isinstance(focus_points, list):
        for point in focus_points:
            if isinstance(point, dict):
                scale_point_around_center(point, center, scale)

    # Scale forecast-next uncertainty and footprint
    forecast_next = storm_state.get("forecast_next")
    if isinstance(forecast_next, dict):
        for _, item in forecast_next.items():
            if not isinstance(item, dict):
                continue

            if "center_range_km" in item:
                item["center_range_km"] = scale_scalar(item["center_range_km"], scale, as_int=False, digits=1)

            fr = item.get("wind_radii_km")
            if isinstance(fr, dict):
                for key in ("r34", "r50", "r64"):
                    if key in fr:
                        fr[key] = scale_range(fr[key], scale, as_int=True)


def move_storm_state(storm_state: Dict[str, Any], dlat: float, dlon: float) -> None:
    """Move one storm_state track instance and its related spatial points."""
    center = storm_state.get("storm_center")
    if isinstance(center, dict):
        shift_point(center, dlat, dlon)

    focus_points = storm_state.get("focus_points")
    if isinstance(focus_points, list):
        for point in focus_points:
            if isinstance(point, dict):
                shift_point(point, dlat, dlon)

    forecast_next = storm_state.get("forecast_next")
    if isinstance(forecast_next, dict):
        for _, item in forecast_next.items():
            if not isinstance(item, dict):
                continue
            next_center = item.get("storm_center")
            if isinstance(next_center, dict):
                shift_point(next_center, dlat, dlon)


def move_location_and_predictions(data: Dict[str, Any], dlat: float, dlon: float) -> None:
    """Optionally move root location and prediction-summary coordinates."""
    location = data.get("location")
    if isinstance(location, dict):
        shift_latlon_fields(location, "latitude", "longitude", dlat, dlon)

    for timestep in data.get("timesteps", []):
        if not isinstance(timestep, dict):
            continue

        ps = timestep.get("prediction_summary")
        if isinstance(ps, dict):
            shift_latlon_fields(ps, "latitude", "longitude", dlat, dlon)

            for hazard_key in ("flood_risk", "severe_weather_risk", "wildfire_spread"):
                hazard = ps.get(hazard_key)
                if isinstance(hazard, dict):
                    shift_latlon_fields(hazard, "latitude", "longitude", dlat, dlon)


def add_transformation_metadata(
    data: Dict[str, Any],
    scale: float,
    moved: bool,
    target_lat: Optional[float],
    target_lon: Optional[float],
    move_location: bool
) -> None:
    """Record what transformation was applied."""
    notes = data.setdefault("transformation_notes", {})
    notes["storm_scale_factor"] = scale
    notes["track_moved"] = moved
    notes["move_location_and_prediction_points"] = move_location

    if moved:
        notes["new_start_coordinate"] = {
            "lat": target_lat,
            "lon": target_lon,
        }


def transform_dataset(
    data: Dict[str, Any],
    scale: float = 1.0,
    target_start_lat: Optional[float] = None,
    target_start_lon: Optional[float] = None,
    move_location: bool = False,
    reverse: bool = False,
) -> Dict[str, Any]:
    """Return a transformed copy of the dataset."""
    if scale <= 0:
        raise ValueError("Scale must be > 0.")

    transformed = deepcopy(data)

    # 0) Reverse timestep order (e.g. make storm approach rather than recede)
    if reverse and isinstance(transformed.get("timesteps"), list):
        transformed["timesteps"] = list(reversed(transformed["timesteps"]))

    # 1) Scale spatial footprint
    if scale != 1.0:
        for timestep in transformed.get("timesteps", []):
            storm_state = timestep.get("storm_state")
            if isinstance(storm_state, dict):
                scale_storm_state(storm_state, scale)

    # 2) Move the storm so first center starts at requested coordinate
    moved = target_start_lat is not None and target_start_lon is not None
    if moved:
        dlat, dlon = compute_translation(transformed, target_start_lat, target_start_lon)

        for timestep in transformed.get("timesteps", []):
            storm_state = timestep.get("storm_state")
            if isinstance(storm_state, dict):
                move_storm_state(storm_state, dlat, dlon)

        if move_location:
            move_location_and_predictions(transformed, dlat, dlon)

    add_transformation_metadata(
        transformed,
        scale=scale,
        moved=moved,
        target_lat=target_start_lat,
        target_lon=target_start_lon,
        move_location=move_location,
    )
    if reverse:
        transformed.setdefault("transformation_notes", {})["timesteps_reversed"] = True

    return transformed

def latlon_distance(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Approximate local distance in degrees, correcting longitude by latitude."""
    mean_lat_rad = math.radians((a["lat"] + b["lat"]) / 2.0)
    dlat = b["lat"] - a["lat"]
    dlon = (b["lon"] - a["lon"]) * math.cos(mean_lat_rad)
    return math.hypot(dlat, dlon)


def compute_track_progress(centers: List[Dict[str, float]]) -> List[float]:
    """
    Return normalized cumulative progress values in [0, 1] for each center.
    This preserves the original pacing of the track.
    """
    if len(centers) <= 1:
        return [0.0] * len(centers)

    cumulative = [0.0]
    total = 0.0

    for i in range(1, len(centers)):
        seg = latlon_distance(centers[i - 1], centers[i])
        total += seg
        cumulative.append(total)

    if total == 0:
        return [i / (len(centers) - 1) for i in range(len(centers))]

    return [x / total for x in cumulative]


def quadratic_bezier(
    p0: Dict[str, float],
    p1: Dict[str, float],
    p2: Dict[str, float],
    t: float
) -> Dict[str, float]:
    """Evaluate a quadratic Bézier curve at t in [0, 1]."""
    one_minus_t = 1.0 - t

    lat = (
        one_minus_t * one_minus_t * p0["lat"]
        + 2.0 * one_minus_t * t * p1["lat"]
        + t * t * p2["lat"]
    )
    lon = (
        one_minus_t * one_minus_t * p0["lon"]
        + 2.0 * one_minus_t * t * p1["lon"]
        + t * t * p2["lon"]
    )

    return {"lat": round_float(lat, 5), "lon": round_float(lon, 5)}


def auto_control_point(
    start: Dict[str, float],
    end: Dict[str, float],
    bend_factor: float
) -> Dict[str, float]:
    """
    Create a control point off the midpoint using a perpendicular offset.
    Positive bend_factor bends to one side; negative bends to the other.
    """
    mid_lat = (start["lat"] + end["lat"]) / 2.0
    mid_lon = (start["lon"] + end["lon"]) / 2.0

    dx = end["lon"] - start["lon"]
    dy = end["lat"] - start["lat"]
    length = math.hypot(dx, dy)

    if length == 0:
        return {"lat": round_float(mid_lat, 5), "lon": round_float(mid_lon, 5)}

    # Perpendicular unit vector
    px = -dy / length
    py = dx / length

    offset = bend_factor * length

    control_lat = mid_lat + py * offset
    control_lon = mid_lon + px * offset

    return {"lat": round_float(control_lat, 5), "lon": round_float(control_lon, 5)}


def set_point(point: Dict[str, Any], lat: float, lon: float) -> None:
    """Set point lat/lon in-place."""
    if "lat" in point and "lon" in point:
        point["lat"] = round_float(lat, 5)
        point["lon"] = round_float(lon, 5)

def remap_track_to_bezier(
    data: Dict[str, Any],
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    control_lat: Optional[float] = None,
    control_lon: Optional[float] = None,
    bend_factor: float = 0.25,
) -> Dict[str, Any]:
    """
    Remap all storm centers onto a curved Bézier track.
    Every timestep gets a local delta, and attached geometry moves with it.
    """
    transformed = deepcopy(data)
    timesteps = transformed.get("timesteps", [])

    if not timesteps:
        raise ValueError("Dataset has no timesteps.")

    original_centers: List[Dict[str, float]] = []
    for timestep in timesteps:
        center = timestep.get("storm_state", {}).get("storm_center")
        if not isinstance(center, dict) or "lat" not in center or "lon" not in center:
            raise ValueError("Every timestep must have storm_state.storm_center.")
        original_centers.append({"lat": center["lat"], "lon": center["lon"]})

    n = len(original_centers)
    progress = [i / (n - 1) if n > 1 else 0.0 for i in range(n)]

    start = {"lat": start_lat, "lon": start_lon}
    end = {"lat": end_lat, "lon": end_lon}

    if control_lat is not None and control_lon is not None:
        control = {"lat": control_lat, "lon": control_lon}
    else:
        control = auto_control_point(start, end, bend_factor)

    new_centers = [quadratic_bezier(start, control, end, t) for t in progress]

    # Map exact times to new centers so forecast_next can follow the same curve
    time_to_new_center: Dict[str, Dict[str, float]] = {}
    for i, timestep in enumerate(timesteps):
        time_key = timestep.get("time")
        if isinstance(time_key, str):
            time_to_new_center[time_key] = new_centers[i]

    for i, timestep in enumerate(timesteps):
        storm_state = timestep.get("storm_state", {})
        old_center = original_centers[i]
        new_center = new_centers[i]

        dlat = new_center["lat"] - old_center["lat"]
        dlon = new_center["lon"] - old_center["lon"]

        # Move current center exactly onto the curve
        center = storm_state.get("storm_center")
        if isinstance(center, dict):
            set_point(center, new_center["lat"], new_center["lon"])

        # Move focus points by local delta
        focus_points = storm_state.get("focus_points")
        if isinstance(focus_points, list):
            for point in focus_points:
                if isinstance(point, dict):
                    shift_point(point, dlat, dlon)

        # Forecast centers: snap to the future curve if that time exists
        forecast_next = storm_state.get("forecast_next")
        if isinstance(forecast_next, dict):
            for _, item in forecast_next.items():
                if not isinstance(item, dict):
                    continue

                fc_time = item.get("forecast_time")
                fc_center = item.get("storm_center")

                if not isinstance(fc_center, dict):
                    continue

                if isinstance(fc_time, str) and fc_time in time_to_new_center:
                    future_center = time_to_new_center[fc_time]
                    set_point(fc_center, future_center["lat"], future_center["lon"])
                else:
                    # fallback: at least preserve local consistency
                    shift_point(fc_center, dlat, dlon)

    notes = transformed.setdefault("transformation_notes", {})
    notes["path_mode"] = "bezier"
    notes["curve_start"] = start
    notes["curve_end"] = end
    notes["curve_control"] = control
    notes["bend_factor"] = bend_factor

    return transformed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scale and/or move a synthetic storm JSON dataset."
    )
    parser.add_argument("input", help="Path to input JSON file")
    parser.add_argument("-o", "--output", help="Path to output JSON file")
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Spatial scale factor. Example: 0.6 makes the storm smaller, 1.5 larger."
    )
    parser.add_argument(
        "--target-start-lat",
        type=float,
        help="Desired latitude for the first timestep storm center"
    )
    parser.add_argument(
        "--target-start-lon",
        type=float,
        help="Desired longitude for the first timestep storm center"
    )
    parser.add_argument(
        "--move-location",
        action="store_true",
        help="Also move root location and prediction_summary lat/lon fields"
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="Overwrite the input file"
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Reverse the timestep order so the storm approaches rather than recedes."
    )

    # New curved-path args
    parser.add_argument(
        "--path-mode",
        choices=["shift", "bezier"],
        default="shift",
        help="How to modify the storm path."
    )
    parser.add_argument("--curve-start-lat", type=float, help="Start latitude for curved path")
    parser.add_argument("--curve-start-lon", type=float, help="Start longitude for curved path")
    parser.add_argument("--curve-end-lat", type=float, help="End latitude for curved path")
    parser.add_argument("--curve-end-lon", type=float, help="End longitude for curved path")
    parser.add_argument("--control-lat", type=float, help="Optional Bézier control-point latitude")
    parser.add_argument("--control-lon", type=float, help="Optional Bézier control-point longitude")
    parser.add_argument(
        "--bend-factor",
        type=float,
        default=0.25,
        help="Auto-generated curve bend amount when no control point is supplied."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if args.inplace and args.output:
        raise ValueError("Use either --inplace or --output, not both.")

    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)


    if args.path_mode == "bezier":
        required = [
            args.curve_start_lat,
            args.curve_start_lon,
            args.curve_end_lat,
            args.curve_end_lon,
        ]
        if any(x is None for x in required):
            raise ValueError(
                "--path-mode bezier requires --curve-start-lat, --curve-start-lon, "
                "--curve-end-lat, and --curve-end-lon."
            )

        transformed = remap_track_to_bezier(
            data=data,
            start_lat=args.curve_start_lat,
            start_lon=args.curve_start_lon,
            end_lat=args.curve_end_lat,
            end_lon=args.curve_end_lon,
            control_lat=args.control_lat,
            control_lon=args.control_lon,
            bend_factor=args.bend_factor,
        )

        if args.scale != 1.0:
            for timestep in transformed.get("timesteps", []):
                storm_state = timestep.get("storm_state")
                if isinstance(storm_state, dict):
                    scale_storm_state(storm_state, args.scale)

    else:
        transformed = transform_dataset(
            data=data,
            scale=args.scale,
            target_start_lat=args.target_start_lat,
            target_start_lon=args.target_start_lon,
            move_location=args.move_location,
            reverse=args.reverse,
        )

    if args.inplace:
        output_path = input_path
    elif args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(f"{input_path.stem}_transformed{input_path.suffix}")

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(transformed, f, indent=2, ensure_ascii=False)

    print(f"Saved transformed dataset to: {output_path}")


if __name__ == "__main__":
    main()