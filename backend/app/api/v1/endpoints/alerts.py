"""Alerts endpoints — unified active disaster signal feed.

The /alerts/signals endpoint returns a merged GeoJSON FeatureCollection
aggregating real-time signals from all configured providers (USGS, NASA
FIRMS, NOAA NWS, GDACS). Provider fetch and normalization logic lives in
alerts_service and the providers layer; this module stays thin.
"""

import asyncio
from typing import List

from fastapi import APIRouter, HTTPException

from app.schemas.alert_models import AlertSignal
from app.services import alerts_service
from app.utils.geo import signal_to_feature

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/signals")
async def list_signals() -> dict:
    """Merged GeoJSON FeatureCollection of active disaster signals.

    Aggregates seismic, wildfire, weather, and global disaster signals
    from all configured providers in parallel. Provider failures are
    suppressed — partial results are returned rather than erroring.
    """
    signals = await alerts_service.fetch_all_signals()
    features = [f for s in signals if (f := signal_to_feature(s)) is not None]
    return {"type": "FeatureCollection", "features": [feat.model_dump() for feat in features]}


@router.get("/signals/source/{source}", response_model=List[AlertSignal])
async def signals_by_source(source: str) -> List[AlertSignal]:
    """Active signals filtered to a single data source.

    Known sources: usgs, nasa-firms, noaa-nws, gdacs.
    Returns an empty list (not 404) when a valid source has no active signals.
    """
    return await alerts_service.fetch_signals_by_source(source)


@router.get("/signals/{signal_id}", response_model=AlertSignal)
async def signal_by_id(signal_id: str) -> AlertSignal:
    """Retrieve a single signal by its provider-assigned ID."""
    signal = await alerts_service.get_signal_by_id(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"Signal '{signal_id}' not found.")
    return signal


# ---------------------------------------------------------------------------
# CLI debugging helper (run this file directly: python -m app.api.v1.endpoints.alerts)
# ---------------------------------------------------------------------------

def _print_signals(signals: List[AlertSignal]) -> None:
    print("\n===== DISASTER SIGNALS =====\n")
    for s in signals:
        lat = f"{s.latitude:.4f}" if s.latitude else "N/A"
        lon = f"{s.longitude:.4f}" if s.longitude else "N/A"
        print(
            f"ID:        {s.id}\n"
            f"TYPE:      {s.signal_type}\n"
            f"SEVERITY:  {s.severity}\n"
            f"SOURCE:    {s.source}\n"
            f"VALUE:     {s.value}\n"
            f"REGION:    {s.region}\n"
            f"LOCATION:  ({lat}, {lon})\n"
            "----------------------------------------"
        )


if __name__ == "__main__":
    signals = asyncio.run(alerts_service.fetch_all_signals())
    _print_signals(signals)
