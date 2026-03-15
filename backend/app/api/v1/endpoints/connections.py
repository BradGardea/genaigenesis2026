from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.relationship_models import (
    HelpNeededConnectionsResponse,
    PersonConnectionsResponse,
)
from app.services.person_relationships_service import (
    get_first_person_connections,
    get_first_person_help_needed,
)

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get(
    "/first",
    response_model=PersonConnectionsResponse,
    summary="Get the first person and their connections from the relationships dataset",
)
async def connections_first(step: int = Query(default=0, ge=0)) -> PersonConnectionsResponse:
    try:
        return await get_first_person_connections(step)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load connections: {exc}",
        ) from exc


@router.get(
    "/help-needed",
    response_model=HelpNeededConnectionsResponse,
    summary="Get direct connections currently flagged as needing help",
)
async def connections_help_needed(step: int = Query(default=0, ge=0)) -> HelpNeededConnectionsResponse:
    try:
        return await get_first_person_help_needed(step)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load connections: {exc}",
        ) from exc
