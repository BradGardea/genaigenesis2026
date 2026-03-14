"""Signal normalization helpers for disaster classification and provider data.

Provides type mapping, normalization functions, and per-provider data
transformers that convert raw API responses into AlertSignal objects.
"""

from typing import Optional, List
from app.schemas.alert_models import AlertSignal

# Abbreviated disaster type codes -> normalized names
TYPE_MAP: dict[str, str] = {
    "eq": "seismic",
    "wf": "wildfire",
    "fl": "flood",
    "dr": "drought",
    "tc": "cyclone",
    "vo": "volcano",
}


def normalize_type(t: Optional[str]) -> str:
    """Map abbreviated or raw disaster type codes to normalized names."""
    if not t:
        return "disaster"
    t = t.lower()
    return TYPE_MAP.get(t, t)


def polygon_center(coords: list) -> tuple[float, float]:
    """Return (lat, lon) centroid of a polygon coordinate ring."""
    lon = sum(p[0] for p in coords) / len(coords)
    lat = sum(p[1] for p in coords) / len(coords)
    return lat, lon


# --------------------------------------------------------------------------
# Per-provider normalization: raw API data -> List[AlertSignal]
# --------------------------------------------------------------------------

def normalize_seismic(features: list) -> List[AlertSignal]:
    """Normalize raw USGS earthquake features into AlertSignals."""
    signals: List[AlertSignal] = []
    for q in features:
        try:
            props = q["properties"]
            coords = q["geometry"]["coordinates"]
            mag = props.get("mag")
            place = props.get("place", "unknown")
            severity = "low"
            if mag and mag >= 6:
                severity = "high"
            elif mag and mag >= 4:
                severity = "medium"
            signals.append(
                AlertSignal(
                    id=q["id"],
                    signal_type="seismic",
                    value=f"M{mag} earthquake near {place}",
                    severity=severity,
                    source="usgs",
                    latitude=coords[1],
                    longitude=coords[0],
                    region=place,
                )
            )
        except (KeyError, TypeError, IndexError):
            continue
    return signals


def normalize_fires(rows: list) -> List[AlertSignal]:
    """Normalize raw NASA FIRMS fire rows into AlertSignals."""
    return [
        AlertSignal(
            id=f"fire-{i}",
            signal_type="wildfire",
            value="thermal anomaly detected",
            severity="medium",
            source="nasa-firms",
            latitude=row["lat"],
            longitude=row["lon"],
        )
        for i, row in enumerate(rows)
    ]


def normalize_weather_alerts(features: list) -> List[AlertSignal]:
    """Normalize raw NOAA NWS alert features into AlertSignals."""
    signals: List[AlertSignal] = []
    for alert in features:
        try:
            props = alert["properties"]
            event = props.get("event", "")
            severity = (props.get("severity") or "unknown").lower()
            lat = lon = None
            geometry = alert.get("geometry")
            if geometry and geometry.get("coordinates"):
                lat, lon = polygon_center(geometry["coordinates"][0])
            signals.append(
                AlertSignal(
                    id=alert["id"],
                    signal_type=normalize_type(event.lower()),
                    value=event,
                    severity=severity,
                    source="noaa-nws",
                    latitude=lat,
                    longitude=lon,
                    region=props.get("areaDesc"),
                )
            )
        except (KeyError, TypeError):
            continue
    return signals


def normalize_gdacs(features: list) -> List[AlertSignal]:
    """Normalize raw GDACS event features into AlertSignals."""
    signals: List[AlertSignal] = []
    for e in features:
        try:
            props = e["properties"]
            coords = e.get("geometry", {}).get("coordinates", [None, None])
            signals.append(
                AlertSignal(
                    id=str(props.get("eventid")),
                    signal_type=normalize_type(props.get("eventtype")),
                    value=str(props.get("name", "unknown")),
                    severity=str(props.get("alertlevel", "unknown")).lower(),
                    source="gdacs",
                    latitude=coords[1] if len(coords) > 1 else None,
                    longitude=coords[0] if len(coords) > 0 else None,
                )
            )
        except (KeyError, TypeError, IndexError):
            continue
    return signals
