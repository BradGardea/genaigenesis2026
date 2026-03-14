"""Geospatial helpers for coordinate math and GeoJSON conversion."""

import math
from typing import Optional, List

from app.schemas.alert_models import AlertSignal, GeoFeature


def signal_to_feature(s: AlertSignal) -> Optional[GeoFeature]:
    """Convert an AlertSignal to a GeoJSON Feature, or None if no coordinates."""
    if s.latitude is None or s.longitude is None:
        return None
    return GeoFeature(
        type="Feature",
        geometry={
            "type": "Point",
            "coordinates": [s.longitude, s.latitude],
        },
        properties={
            "id": s.id,
            "signal_type": s.signal_type,
            "value": s.value,
            "severity": s.severity,
            "source": s.source,
            "region": s.region,
        },
    )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return approximate great-circle distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def filter_signals_near(
    signals: List[AlertSignal],
    lat: float,
    lon: float,
    radius_km: float = 300.0,
) -> List[AlertSignal]:
    """Return signals whose coordinates fall within radius_km of (lat, lon)."""
    nearby: List[AlertSignal] = []
    for s in signals:
        if s.latitude is not None and s.longitude is not None:
            dist = haversine_km(lat, lon, s.latitude, s.longitude)
            if dist <= radius_km:
                nearby.append(s)
    return nearby
