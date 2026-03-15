"""Predefined evacuation points for the Vilankulo, Mozambique scenario.

Each point represents a safe assembly area inland or on high ground,
away from the coastal storm surge and flooding zones.
"""

from __future__ import annotations

import math
from typing import NamedTuple


class EvacuationPoint(NamedTuple):
    name: str
    lat: float
    lng: float
    capacity: int  # approximate person capacity
    type: str      # e.g. "school", "church", "field", "government"


VILANKULO_EVACUATION_POINTS: list[EvacuationPoint] = [
    EvacuationPoint(
        name="North Assembly",
        lat=-21.96057,
        lng=35.29959,
        capacity=800,
        type="field",
    ),
    EvacuationPoint(
        name="Northwest Junction",
        lat=-21.97286,
        lng=35.28916,
        capacity=500,
        type="government",
    ),
    EvacuationPoint(
        name="West Inland Assembly",
        lat=-21.99236,
        lng=35.26070,
        capacity=400,
        type="field",
    ),
    EvacuationPoint(
        name="Southwest Assembly",
        lat=-22.00801,
        lng=35.27525,
        capacity=1200,
        type="field",
    ),
    EvacuationPoint(
        name="South Coastal Assembly",
        lat=-22.03504,
        lng=35.31516,
        capacity=600,
        type="government",
    ),
]


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_evacuation_point(lat: float, lng: float) -> EvacuationPoint:
    """Return the evacuation point closest to the given coordinate."""
    return min(
        VILANKULO_EVACUATION_POINTS,
        key=lambda ep: _haversine_km(lat, lng, ep.lat, ep.lng),
    )


def sorted_evacuation_points(lat: float, lng: float) -> list[tuple[EvacuationPoint, float]]:
    """Return all evacuation points sorted by distance (nearest first), with distance in km."""
    scored = [
        (ep, _haversine_km(lat, lng, ep.lat, ep.lng))
        for ep in VILANKULO_EVACUATION_POINTS
    ]
    scored.sort(key=lambda x: x[1])
    return scored
