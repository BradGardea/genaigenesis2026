"""Normalization helpers for tropical storm data.

Converts raw provider payloads (NHC CurrentStorms JSON, JTWC RSS, etc.)
into the internal storm schema models. All provider-specific field
names are resolved here so that the service layer stays clean.
"""

from typing import Optional
import re

from app.schemas.storm_models import (
    ActiveStormItem,
    StormDetail,
    StormTrackPoint,
    StormForecastPoint,
    StormWindRadii,
)

# Nautical miles to km conversion factor
NM_TO_KM = 1.852

# Human-readable basin labels
BASIN_LABELS: dict[str, str] = {
    "al": "al",
    "ep": "ep",
    "cp": "cp",
    "wp": "wp",
    "io": "io",
    "sh": "sh",
}


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------


def parse_nhc_lat(value: object) -> Optional[float]:
    """Parse NHC latitude string ('24.5N' or '10.2S') or numeric to float.

    Southern hemisphere values become negative.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().upper()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([NS])$", s)
    if m:
        deg = float(m.group(1))
        return deg if m.group(2) == "N" else -deg
    try:
        return float(s)
    except ValueError:
        return None


def parse_nhc_lon(value: object) -> Optional[float]:
    """Parse NHC longitude string ('77.7W' or '120.3E') or numeric to float.

    Western hemisphere values become negative.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().upper()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([EW])$", s)
    if m:
        deg = float(m.group(1))
        return deg if m.group(2) == "E" else -deg
    try:
        return float(s)
    except ValueError:
        return None


def extract_basin(storm_id: str) -> str:
    """Derive basin code from the first two characters of a storm ID.

    NHC uses 'al', 'ep', 'cp'; JTWC uses 'wp', 'io', 'sh'.
    Defaults to 'al' for unknown prefixes.
    """
    prefix = storm_id[:2].lower() if len(storm_id) >= 2 else ""
    return BASIN_LABELS.get(prefix, "al")


def nm_to_km(nm: object) -> Optional[float]:
    """Convert nautical miles to kilometres. Returns None for falsy inputs."""
    if nm is None:
        return None
    try:
        val = float(nm)
        return round(val * NM_TO_KM, 1) if val > 0 else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Wind radii parsing
# ---------------------------------------------------------------------------


def parse_wind_radii_block(radii_dict: dict, wind_speed_kt: int) -> Optional[StormWindRadii]:
    """Parse one wind-radii quadrant block for a given kt threshold.

    Accepts keys in several formats:
      - {"NE": 200, "SE": 150, ...}          (NHC numeric, values in nm)
      - {"ne": 200, ...}                      (lowercase)
    Returns None if all quadrant values are zero or missing.
    """
    if not isinstance(radii_dict, dict):
        return None
    ne = nm_to_km(radii_dict.get("NE") or radii_dict.get("ne"))
    se = nm_to_km(radii_dict.get("SE") or radii_dict.get("se"))
    sw = nm_to_km(radii_dict.get("SW") or radii_dict.get("sw"))
    nw = nm_to_km(radii_dict.get("NW") or radii_dict.get("nw"))
    # Skip if all quadrants are absent / zero
    if not any([ne, se, sw, nw]):
        return None
    return StormWindRadii(wind_speed_kt=wind_speed_kt, ne_km=ne, se_km=se, sw_km=sw, nw_km=nw)


def parse_nhc_wind_radii(raw: dict) -> list[StormWindRadii]:
    """Extract all wind-radii thresholds from an NHC storm object.

    Looks for an 'initialWindRadii' block (or similar) keyed by '34kt', '50kt', '64kt'.
    """
    radii_block = (
        raw.get("initialWindRadii")
        or raw.get("windRadii")
        or raw.get("wind_radii")
        or {}
    )
    if not isinstance(radii_block, dict):
        return []

    result: list[StormWindRadii] = []
    kt_map = {"34kt": 34, "50kt": 50, "64kt": 64, "34": 34, "50": 50, "64": 64}
    for key, kt in kt_map.items():
        block = radii_block.get(key)
        if isinstance(block, dict):
            radii = parse_wind_radii_block(block, kt)
            if radii:
                result.append(radii)
    return result


# ---------------------------------------------------------------------------
# NHC raw dict → schema models
# ---------------------------------------------------------------------------


def nhc_to_active_storm(raw: dict) -> Optional[ActiveStormItem]:
    """Convert a raw NHC storm dict to an ActiveStormItem.

    Handles both numeric and string lat/lon fields. Returns None if the
    minimum required fields (storm_id, name) cannot be resolved.
    """
    try:
        storm_id = str(raw.get("id") or raw.get("stormId") or "").lower()
        name = str(raw.get("name") or raw.get("Name") or "UNNAMED").upper()
        if not storm_id:
            return None

        # Prefer pre-parsed numeric fields when available
        lat = raw.get("latitudeNumeric") or parse_nhc_lat(raw.get("latitude"))
        lon = raw.get("longitudeNumeric") or parse_nhc_lon(raw.get("longitude"))

        intensity = raw.get("intensity") or raw.get("maxWind") or raw.get("maxSustainedWind")
        pressure = raw.get("pressure") or raw.get("minPressure") or raw.get("centralPressure")

        classification = str(
            raw.get("classification") or raw.get("stormType") or "TD"
        ).upper()

        return ActiveStormItem(
            storm_id=storm_id,
            name=name,
            basin=extract_basin(storm_id),
            classification=classification,
            intensity_kt=int(intensity) if intensity is not None else None,
            pressure_mb=float(pressure) if pressure is not None else None,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            movement_dir_deg=_safe_int(raw.get("movementDir") or raw.get("movDir")),
            movement_speed_kt=_safe_float(
                raw.get("movementSpeed") or raw.get("movSpeed")
            ),
            last_update=str(raw.get("lastUpdate") or raw.get("lastAdvisory") or ""),
            headline=str(raw.get("headline") or raw.get("publicHeadline") or ""),
            source="nhc",
        )
    except Exception:
        return None


def nhc_to_storm_detail(raw: dict) -> Optional[StormDetail]:
    """Convert a raw NHC storm dict to a full StormDetail record."""
    base = nhc_to_active_storm(raw)
    if base is None:
        return None

    pub_adv = raw.get("publicAdvisory") or {}
    fct_adv = raw.get("forecastAdvisory") or raw.get("advisoryDiscussion") or {}

    return StormDetail(
        storm_id=base.storm_id,
        name=base.name,
        basin=base.basin,
        classification=base.classification,
        intensity_kt=base.intensity_kt,
        pressure_mb=base.pressure_mb,
        latitude=base.latitude,
        longitude=base.longitude,
        movement_dir_deg=base.movement_dir_deg,
        movement_speed_kt=base.movement_speed_kt,
        last_update=base.last_update,
        headline=base.headline,
        source="nhc",
        public_advisory_url=_safe_str(pub_adv.get("url")),
        forecast_advisory_url=_safe_str(fct_adv.get("url")),
        current_wind_radii=parse_nhc_wind_radii(raw),
    )


def nhc_raw_track_to_points(raw_points: list[dict]) -> list[StormTrackPoint]:
    """Convert a list of raw NHC best-track or observed position dicts to StormTrackPoints."""
    points: list[StormTrackPoint] = []
    for p in raw_points:
        try:
            lat = p.get("latitudeNumeric") or parse_nhc_lat(p.get("latitude"))
            lon = p.get("longitudeNumeric") or parse_nhc_lon(p.get("longitude"))
            if lat is None or lon is None:
                continue
            points.append(
                StormTrackPoint(
                    time=str(
                        p.get("validTime") or p.get("time") or p.get("date") or ""
                    ),
                    latitude=float(lat),
                    longitude=float(lon),
                    max_wind_kt=_safe_int(
                        p.get("maxWind") or p.get("intensity") or p.get("maxSustainedWind")
                    ),
                    min_pressure_mb=_safe_float(
                        p.get("minPressure") or p.get("pressure")
                    ),
                    classification=_safe_str(
                        p.get("classification") or p.get("stormType")
                    ),
                )
            )
        except Exception:
            continue
    return points


def nhc_raw_forecast_to_points(raw_points: list[dict]) -> list[StormForecastPoint]:
    """Convert raw NHC forecastTrack entries to StormForecastPoints."""
    points: list[StormForecastPoint] = []
    for p in raw_points:
        try:
            lat = p.get("latitudeNumeric") or parse_nhc_lat(p.get("latitude"))
            lon = p.get("longitudeNumeric") or parse_nhc_lon(p.get("longitude"))
            if lat is None or lon is None:
                continue
            # Nested wind radii inside a forecast point
            radii: list[StormWindRadii] = []
            radii_block = p.get("windRadii") or p.get("wind_radii") or {}
            if isinstance(radii_block, dict):
                for kt_key, kt_val in {"34kt": 34, "50kt": 50, "64kt": 64}.items():
                    block = radii_block.get(kt_key)
                    if isinstance(block, dict):
                        r = parse_wind_radii_block(block, kt_val)
                        if r:
                            radii.append(r)

            points.append(
                StormForecastPoint(
                    valid_time=str(
                        p.get("validTime") or p.get("time") or p.get("forecastTime") or ""
                    ),
                    latitude=float(lat),
                    longitude=float(lon),
                    max_wind_kt=_safe_int(
                        p.get("maxWind") or p.get("intensity") or p.get("maxSustainedWind")
                    ),
                    min_pressure_mb=_safe_float(
                        p.get("minPressure") or p.get("pressure")
                    ),
                    classification=_safe_str(
                        p.get("classification") or p.get("stormType")
                    ),
                    wind_radii=radii,
                )
            )
        except Exception:
            continue
    return points


# ---------------------------------------------------------------------------
# Small private coercion helpers
# ---------------------------------------------------------------------------


def _safe_int(v: object) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(v: object) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_str(v: object) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None
