"""Storm endpoints — active storm list, detail, track, geometry, and forecast.

These endpoints expose structured tropical cyclone data with explicit
geometry fields (eye position, wind radii, forecast cone). They are
intentionally separate from the /forecasts and /predictions endpoints,
which are point-based and do not carry storm geometry.

Route order: /active must come before /{storm_id} so FastAPI does not
capture the literal string "active" as a storm_id path parameter.
"""

from fastapi import APIRouter, HTTPException

from app.schemas.storm_models import (
    ActiveStormsResponse,
    StormDetail,
    StormTrackResponse,
    StormGeometrySnapshot,
    StormForecastResponse,
)
from app.services import storms_service

router = APIRouter(prefix="/storms", tags=["storms"])


@router.get("/active", response_model=ActiveStormsResponse)
async def active_storms() -> ActiveStormsResponse:
    """List all currently active tropical storms.

    Combines data from NHC (Atlantic/East-Pacific) and JTWC
    (West-Pacific/Indian Ocean/Southern Hemisphere). Returns an empty
    list outside active storm seasons; never returns an error for empty
    provider responses.
    """
    return await storms_service.get_active_storms()


@router.get("/{storm_id}", response_model=StormDetail)
async def storm_detail(storm_id: str) -> StormDetail:
    """Full detail for a single active storm.

    ``storm_id`` is the NHC/JTWC identifier, e.g. ``al012025`` or ``wp022025``.
    Returns 404 if the storm is not currently active in any provider feed.
    """
    detail = await storms_service.get_storm_detail(storm_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Storm '{storm_id}' is not currently active. "
            "Check /storms/active for the list of active storms.",
        )
    return detail


@router.get("/{storm_id}/track", response_model=StormTrackResponse)
async def storm_track(storm_id: str) -> StormTrackResponse:
    """Observed track and near-term forecast positions for a storm.

    Currently surfaces the current position plus any forecast-track
    points embedded in the NHC advisory JSON. Full historical best-track
    data (IBTrACS integration) is a planned follow-up.

    Always returns 200; the ``track`` list may contain only the current
    position or be empty if the storm is not found.
    """
    return await storms_service.get_storm_track(storm_id)


@router.get("/{storm_id}/geometry", response_model=StormGeometrySnapshot)
async def storm_geometry(storm_id: str) -> StormGeometrySnapshot:
    """Current-time geometry snapshot: center position and wind-radii rings.

    ``wind_radii`` contains 34/50/64-kt quadrant extents when the NHC
    provides them. ``cone_geojson`` is the 5-day forecast cone polygon
    from the NHC advisory GeoJSON; it will be ``null`` when the advisory
    is not yet published or unavailable.

    Always returns 200; fields are null-safe for missing provider data.
    """
    return await storms_service.get_storm_geometry(storm_id)


@router.get("/{storm_id}/forecast", response_model=StormForecastResponse)
async def storm_forecast(storm_id: str) -> StormForecastResponse:
    """5-day forecast track and intensity guidance for a storm.

    ``forecast_points`` are the official NHC forecast positions (0h through
    120h). ``cone_geojson`` is the forecast cone polygon when available from
    the NHC advisory GeoJSON endpoint.

    Always returns 200; lists are empty and a ``note`` is set when data
    is unavailable.
    """
    return await storms_service.get_storm_forecast(storm_id)
