from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/routes", tags=["routes"])


class EvacuationProfile(BaseModel):
    family_size: int = Field(ge=1)
    vehicles: int = Field(ge=0)
    has_children: bool = False
    has_elderly: bool = False
    has_mobility_needs: bool = False


class RoutePlan(BaseModel):
    id: str
    summary: str
    primary_route: str
    backup_route: str
    checklist: list[str]


@router.post("/plan", response_model=RoutePlan)
def build_route_plan(profile: EvacuationProfile) -> RoutePlan:
    checklist = [
        "Charge phones and battery banks",
        "Pack IDs, medications, and water",
        "Monitor official updates every 10 minutes",
    ]

    if profile.has_children:
        checklist.append("Pack child-specific supplies and comfort items")
    if profile.has_elderly or profile.has_mobility_needs:
        checklist.append("Prioritize accessible shelters and transport support")

    return RoutePlan(
        id="plan-demo-1",
        summary="Prototype evacuation plan generated",
        primary_route="Use Highway 7 southbound to Shelter A",
        backup_route="Use County Road 14 to Shelter C",
        checklist=checklist,
    )

