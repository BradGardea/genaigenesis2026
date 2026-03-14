"""NOAA / NWS active weather alerts provider.

Fetches active weather alert features from the NWS API.
Normalization is handled by the service/normalization layer.
"""

from typing import Any
import httpx

from app.core.constants import NOAA_ALERTS_URL


async def fetch_raw_alerts(
    client: httpx.AsyncClient, limit: int = 10
) -> list[dict[str, Any]]:
    """Fetch raw active alert features from NOAA NWS.

    Returns at most `limit` features. Returns an empty list on any error.
    """
    try:
        r = await client.get(NOAA_ALERTS_URL)
        r.raise_for_status()
        data = r.json()
        return data.get("features", [])[:limit]
    except Exception:
        return []
