import json
import sys
from pathlib import Path
from typing import Any


TOP_LEVEL_REQUIRED = {
    "location": dict,
    "timesteps": list,
}

TIMESTEP_REQUIRED = {
    "time": str,
    "weather": dict,
    "prediction_summary": dict,
    "storm_state": dict,
    "evacuation_signal": dict,
}

WEATHER_REQUIRED = {
    "temperature_c": (int, float),
    "wind_speed_kmh": (int, float),
    "precipitation_probability": int,
    "relative_humidity": int,
}

PREDICTION_SUMMARY_REQUIRED = {
    "latitude": (int, float),
    "longitude": (int, float),
    "generated_at": str,
    "note": str,
}

STORM_CENTER_REQUIRED = {
    "lat": (int, float),
    "lon": (int, float),
}

WIND_RADII_REQUIRED = {
    "r34": (int, float),
    "r50": (int, float),
}

EVAC_SIGNAL_REQUIRED = {
    "status": str,
    "recommended_action": str,
    "primary_trigger": str,
}


def type_name(expected: Any) -> str:
    if isinstance(expected, tuple):
        return " or ".join(t.__name__ for t in expected)
    return expected.__name__


def add_error(errors: list[str], msg: str) -> None:
    errors.append(msg)


def check_required_fields(
    obj: Any,
    required: dict[str, Any],
    errors: list[str],
    path: str,
) -> None:
    if not isinstance(obj, dict):
        add_error(errors, f"{path}: expected object, got {type(obj).__name__}")
        return

    for field, expected_type in required.items():
        if field not in obj:
            add_error(errors, f"{path}.{field}: missing field")
            continue

        value = obj[field]
        if not isinstance(value, expected_type):
            add_error(
                errors,
                f"{path}.{field}: expected {type_name(expected_type)}, got {type(value).__name__}",
            )


def check_optional_prediction(pred: Any, errors: list[str], path: str) -> None:
    if pred is None:
        return

    if not isinstance(pred, dict):
        add_error(errors, f"{path}: expected object or null, got {type(pred).__name__}")
        return

    required = {
        "hazard_type": str,
        "latitude": (int, float),
        "longitude": (int, float),
        "valid_from": str,
        "valid_to": str,
        "risk_level": str,
        "confidence": str,
        "score": int,
        "drivers": list,
        "based_on": list,
        "summary": str,
    }
    check_required_fields(pred, required, errors, path)


def check_focus_points(focus_points: Any, errors: list[str], path: str) -> None:
    if not isinstance(focus_points, list):
        add_error(errors, f"{path}: expected list, got {type(focus_points).__name__}")
        return

    for i, fp in enumerate(focus_points):
        fp_path = f"{path}[{i}]"
        required = {
            "name": str,
            "lat": (int, float),
            "lon": (int, float),
        }
        check_required_fields(fp, required, errors, fp_path)


def check_forecast_next(forecast_next: Any, errors: list[str], path: str) -> None:
    if not isinstance(forecast_next, dict):
        add_error(errors, f"{path}: expected object, got {type(forecast_next).__name__}")
        return

    for horizon in ("30min", "60min", "90min"):
        if horizon not in forecast_next:
            add_error(errors, f"{path}.{horizon}: missing field")
            continue

        item = forecast_next[horizon]
        item_path = f"{path}.{horizon}"
        required = {
            "center_range_km": (int, float),
            "wind_speed_kmh_range": list,
            "precipitation_probability_range": list,
        }
        check_required_fields(item, required, errors, item_path)

        if isinstance(item, dict):
            for list_field in ("wind_speed_kmh_range", "precipitation_probability_range"):
                if list_field in item and isinstance(item[list_field], list):
                    vals = item[list_field]
                    if len(vals) != 2:
                        add_error(errors, f"{item_path}.{list_field}: expected list of length 2, got {len(vals)}")
                    else:
                        for j, val in enumerate(vals):
                            if not isinstance(val, (int, float)):
                                add_error(
                                    errors,
                                    f"{item_path}.{list_field}[{j}]: expected int or float, got {type(val).__name__}",
                                )


def check_timestep(ts: Any, idx: int, errors: list[str]) -> None:
    path = f"timesteps[{idx}]"
    check_required_fields(ts, TIMESTEP_REQUIRED, errors, path)

    if not isinstance(ts, dict):
        return

    if "weather" in ts:
        check_required_fields(ts["weather"], WEATHER_REQUIRED, errors, f"{path}.weather")

    if "prediction_summary" in ts:
        check_required_fields(
            ts["prediction_summary"],
            PREDICTION_SUMMARY_REQUIRED,
            errors,
            f"{path}.prediction_summary",
        )

        ps = ts["prediction_summary"]
        if isinstance(ps, dict):
            check_optional_prediction(ps.get("wildfire_spread"), errors, f"{path}.prediction_summary.wildfire_spread")
            check_optional_prediction(ps.get("flood_risk"), errors, f"{path}.prediction_summary.flood_risk")
            check_optional_prediction(
                ps.get("severe_weather_risk"),
                errors,
                f"{path}.prediction_summary.severe_weather_risk",
            )

    if "storm_state" in ts:
        ss = ts["storm_state"]
        ss_path = f"{path}.storm_state"
        if isinstance(ss, dict):
            if "storm_center" in ss:
                check_required_fields(ss["storm_center"], STORM_CENTER_REQUIRED, errors, f"{ss_path}.storm_center")
            else:
                add_error(errors, f"{ss_path}.storm_center: missing field")

            if "wind_radii_km" in ss:
                check_required_fields(ss["wind_radii_km"], WIND_RADII_REQUIRED, errors, f"{ss_path}.wind_radii_km")
            else:
                add_error(errors, f"{ss_path}.wind_radii_km: missing field")

            if "focus_points" in ss:
                check_focus_points(ss["focus_points"], errors, f"{ss_path}.focus_points")
            else:
                add_error(errors, f"{ss_path}.focus_points: missing field")

            if "forecast_next" in ss:
                check_forecast_next(ss["forecast_next"], errors, f"{ss_path}.forecast_next")
            else:
                add_error(errors, f"{ss_path}.forecast_next: missing field")

    if "evacuation_signal" in ts:
        check_required_fields(ts["evacuation_signal"], EVAC_SIGNAL_REQUIRED, errors, f"{path}.evacuation_signal")


def verify_json_file(file_path: str) -> int:
    path = Path(file_path)

    if not path.exists():
        print(f"ERROR: File does not exist: {path}")
        return 1

    if not path.is_file():
        print(f"ERROR: Path is not a file: {path}")
        return 1

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print("INVALID JSON")
        print(f"Message: {exc.msg}")
        print(f"Line: {exc.lineno}, Column: {exc.colno}, Char: {exc.pos}")
        return 1
    except OSError as exc:
        print(f"ERROR: Could not read file: {exc}")
        return 1

    errors: list[str] = []

    check_required_fields(data, TOP_LEVEL_REQUIRED, errors, "root")

    if not isinstance(data, dict):
        print("INVALID SHAPE: top-level JSON must be an object")
        return 1

    timesteps = data.get("timesteps")
    if isinstance(timesteps, list):
        for idx, ts in enumerate(timesteps):
            check_timestep(ts, idx, errors)

    if errors:
        print("INVALID JSON SHAPE")
        for err in errors:
            print(f"- {err}")
        return 1

    print("VALID JSON")
    print(f"Timestep count: {len(timesteps)}")
    return 0


if __name__ == "__main__":

    sys.exit(verify_json_file("./goma_severe_storm_12h_72_timesteps.json"))