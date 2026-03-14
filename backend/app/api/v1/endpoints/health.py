from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

