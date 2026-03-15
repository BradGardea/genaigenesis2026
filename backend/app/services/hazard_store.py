from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, mapping, shape

from app.models.routing import HazardReport, HazardZone, SSEEvent

logger = logging.getLogger(__name__)


@dataclass
class RouteSubscription:
    route_id: str
    origin: tuple[float, float]
    destination: tuple[float, float]
    geometry: LineString
    queue: asyncio.Queue[SSEEvent] = field(default_factory=asyncio.Queue)


class HazardStore:
    """In-memory hazard and active-route registry."""

    def __init__(self) -> None:
        self._hazards: dict[str, HazardReport] = {}
        self._zones: dict[str, HazardZone] = {}
        self._routes: dict[str, RouteSubscription] = {}

    # ── Hazard CRUD ──────────────────────────────────────────

    def add_hazard(self, report: HazardReport) -> HazardZone:
        self._hazards[report.id] = report
        polygon = self._buffer_polygon(report)
        zone = HazardZone(
            hazard_id=report.id,
            polygon=polygon,
            hazard_type=report.hazard_type,
            severity="high",
            radius_meters=report.radius_meters,
        )
        self._zones[report.id] = zone
        return zone

    def get_hazard(self, hazard_id: str) -> HazardReport | None:
        return self._hazards.get(hazard_id)

    def deactivate_hazard(self, hazard_id: str) -> bool:
        report = self._hazards.get(hazard_id)
        if report is None:
            return False
        report.active = False
        self._zones.pop(hazard_id, None)
        return True

    def get_active_hazards(self) -> list[HazardZone]:
        return [
            zone
            for hid, zone in self._zones.items()
            if self._hazards.get(hid, HazardReport(hazard_type="", location={"lng": 0, "lat": 0})).active
        ]

    def get_active_hazard_polygons(self) -> list[dict]:
        """Return shapely-compatible polygon dicts for active hazards."""
        return [zone.polygon for zone in self.get_active_hazards()]

    # ── Route subscriptions ──────────────────────────────────

    def register_route(
        self,
        route_id: str,
        origin: tuple[float, float],
        destination: tuple[float, float],
        geometry_geojson: dict,
    ) -> RouteSubscription:
        geom = shape(geometry_geojson)
        if not isinstance(geom, LineString):
            raise ValueError("Route geometry must be a LineString")
        sub = RouteSubscription(
            route_id=route_id,
            origin=origin,
            destination=destination,
            geometry=geom,
        )
        self._routes[route_id] = sub
        return sub

    def unregister_route(self, route_id: str) -> None:
        self._routes.pop(route_id, None)

    def get_subscription(self, route_id: str) -> RouteSubscription | None:
        return self._routes.get(route_id)

    async def notify_affected_routes(self, new_zone: HazardZone) -> list[str]:
        """Check all active routes for intersection with new hazard.

        Returns list of affected route IDs. Pushes reroute SSE events to
        affected subscriptions (actual reroute computation is handled by
        the caller / endpoint layer).
        """
        hazard_poly = shape(new_zone.polygon)
        affected: list[str] = []
        for route_id, sub in list(self._routes.items()):
            if sub.geometry.intersects(hazard_poly):
                affected.append(route_id)
                event = SSEEvent(
                    event_type="reroute",
                    data={
                        "reason": "new_hazard",
                        "hazard_id": new_zone.hazard_id,
                        "hazard_type": new_zone.hazard_type,
                    },
                )
                await sub.queue.put(event)
        return affected

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _buffer_polygon(report: HazardReport) -> dict:
        """Create a GeoJSON polygon by buffering the reported point.

        Uses a rough degree approximation (1° ≈ 111 km at equator).
        """
        point = Point(report.location.lng, report.location.lat)
        radius_deg = report.radius_meters / 111_000
        buffered = point.buffer(radius_deg, quad_segs=32)
        return mapping(buffered)


# Singleton store — shared across the application lifetime.
hazard_store = HazardStore()
