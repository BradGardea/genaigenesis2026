from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.models.routing import RouteRequest, RouteResponse
from app.services.hazard_store import hazard_store
from app.services.mapbox_routing import compute_route

router = APIRouter(prefix="/routes", tags=["routes"])


@router.post(
    "/plan",
    response_model=RouteResponse,
    summary="Plan an evacuation route",
    description="""Compute a driving route from origin to destination that avoids all
currently active hazard zones.

### Algorithm

1. **Hazard collection** – fetch every active `HazardZone` from the in-memory
   hazard store.  Each zone is a GeoJSON Polygon produced by buffering the
   reported point by its `radius_meters`.

2. **Avoidance waypoint generation** – for each hazard whose centroid falls
   between the 5 %–95 % projection range along the origin→destination line:
   * Project the centroid onto that line.
   * Compute the perpendicular vector from the projection to the centroid.
   * Place a waypoint on the **opposite side** of the line, offset by
     `radius_deg × repulsion_factor` (initial repulsion = 1.5).

3. **Mapbox Directions request** – send
   `origin → [waypoints…] → destination` to the Mapbox Driving Directions
   API, requesting full GeoJSON geometry and turn-by-turn steps.

4. **Intersection check & retry** – if the returned geometry still intersects
   any hazard polygon (Shapely `LineString.intersects(Polygon)`), double the
   `repulsion_factor` and repeat from step 2.  Up to **2 retries** are
   attempted (3 total calls max).  If the route still intersects after all
   retries it is returned as-is (best effort).

5. **Response assembly** – extract turn-by-turn instructions from each leg's
   steps, record which hazards were avoided, and register the route in the
   hazard store for live SSE updates.

### Real-time rerouting

After the route is planned the client opens an SSE stream on
`GET /routes/{route_id}/stream`.  When a new hazard is reported via
`POST /hazards/report`, the hazard store checks all registered route
geometries for intersection with the new hazard polygon and pushes a
`reroute` event to affected streams.  The client can then call
`POST /routes/plan` again to obtain an updated route.
""",
    responses={
        200: {
            "description": "Successfully planned route with hazard avoidance",
            "content": {
                "application/json": {
                    "example": {
                        "route_id": "route-a1b2c3d4",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-118.25, 34.05], [-118.30, 34.06]],
                        },
                        "distance_meters": 12500.0,
                        "duration_seconds": 840.0,
                        "waypoints": [{"lng": -118.27, "lat": 34.07}],
                        "hazards_avoided": ["haz-deadbeef"],
                        "instructions": [
                            "Head north on Main St",
                            "Turn right onto 1st Ave",
                        ],
                        "backup_route": None,
                    }
                }
            },
        },
    },
)
async def plan_route(body: RouteRequest) -> RouteResponse:
    active_zones = hazard_store.get_active_hazards()
    hazard_polygons = [z.polygon for z in active_zones]

    route = await compute_route(body.origin, body.destination, hazard_polygons)

    route_id = f"route-{uuid.uuid4().hex[:8]}"

    # Extract turn-by-turn instructions and per-segment durations from Mapbox legs
    instructions: list[str] = []
    segment_durations: list[float] = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            text = step.get("maneuver", {}).get("instruction")
            if text:
                instructions.append(text)
        ann = leg.get("annotation", {})
        segment_durations.extend(ann.get("duration", []))

    # Register for live SSE updates
    hazard_store.register_route(
        route_id=route_id,
        origin=(body.origin.lng, body.origin.lat),
        destination=(body.destination.lng, body.destination.lat),
        geometry_geojson=route["geometry"],
    )

    return RouteResponse(
        route_id=route_id,
        geometry=route["geometry"],
        distance_meters=route.get("distance", 0),
        duration_seconds=route.get("duration", 0),
        waypoints=[
            {"lng": wp["lng"], "lat": wp["lat"]}
            for wp in route.get("_avoidance_waypoints", [])
        ],
        hazards_avoided=[z.hazard_id for z in active_zones],
        instructions=instructions,
        segment_durations=segment_durations,
    )


@router.get(
    "/{route_id}/stream",
    summary="Stream live route updates (SSE)",
    description="""Open a Server-Sent Events stream for a previously planned route.

The stream emits the following event types:

| Event type       | Trigger                                     | Data payload                          |
|------------------|---------------------------------------------|---------------------------------------|
| `reroute`        | A newly reported hazard intersects this route | `{"reason":"new_hazard","hazard_id":"…","hazard_type":"…"}` |
| `hazard_removed` | A hazard affecting this route is deactivated  | `{"hazard_id":"…"}`                   |
| heartbeat (comment) | No events for 30 s                       | empty                                 |

The connection stays open until the client disconnects.  On disconnect the
route is automatically unregistered from the hazard store.

**Client usage** – on receiving a `reroute` event the client should call
`POST /routes/plan` again with the same origin/destination to get an updated
route that avoids the new hazard.
""",
    responses={
        200: {"description": "SSE stream opened", "content": {"text/event-stream": {}}},
        404: {"description": "Route ID not found or already unregistered"},
    },
)
async def stream_route_updates(route_id: str, request: Request) -> StreamingResponse:
    sub = hazard_store.get_subscription(route_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Route not found")

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=30)
                    yield f"event: {event.event_type}\ndata: {event.data}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            hazard_store.unregister_route(route_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
