from fastapi import APIRouter, HTTPException, status

from app.schemas.relationship_models import PersonConnectionsResponse
from app.services.person_relationships_service import get_first_person_connections

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get(
    "/first",
    response_model=PersonConnectionsResponse,
    summary="Get the first person and their connections from the relationships dataset",
)
async def connections_first() -> PersonConnectionsResponse:
    try:
        return await get_first_person_connections()
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load connections: {exc}",
        ) from exc
