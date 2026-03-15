from fastapi import APIRouter, HTTPException

from app.models.routing import HazardReport, HazardZone
from app.services.hazard_store import hazard_store

router = APIRouter(prefix="/hazards", tags=["hazards"])


@router.post(
    "/report",
    response_model=HazardZone,
    summary="Report a hazard",
    description="""Register a new hazard (wildfire, flood, roadblock, chemical, other).

The reported point is buffered by `radius_meters` (default 500 m) to create a
GeoJSON Polygon hazard zone.  After storage, every currently registered
evacuation route is checked for intersection with the new zone — affected
routes receive a `reroute` SSE event.
""",
)
async def report_hazard(report: HazardReport) -> HazardZone:
    zone = hazard_store.add_hazard(report)
    await hazard_store.notify_affected_routes(zone)
    return zone


@router.get(
    "/active",
    response_model=list[HazardZone],
    summary="List active hazard zones",
    description="Return every hazard zone that has not been deactivated.",
)
def get_active_hazards() -> list[HazardZone]:
    return hazard_store.get_active_hazards()


@router.delete(
    "/{hazard_id}",
    summary="Deactivate a hazard",
    description="Mark a hazard as inactive. It will no longer be considered during route planning.",
)
def delete_hazard(hazard_id: str) -> dict[str, str]:
    if not hazard_store.deactivate_hazard(hazard_id):
        raise HTTPException(status_code=404, detail="Hazard not found")
    return {"status": "deactivated", "hazard_id": hazard_id}
