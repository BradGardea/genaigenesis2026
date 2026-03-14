"""USGS Earthquake feed provider.

Fetches raw earthquake feature data from the USGS GeoJSON hourly feed.
Normalization is handled by the service/normalization layer, not here.
"""

from typing import Any
import httpx

from app.core.constants import USGS_FEED


async def fetch_raw_seismic(
    client: httpx.AsyncClient, limit: int = 10
) -> list[dict[str, Any]]:
    """Fetch raw earthquake features from the USGS hourly GeoJSON feed.

    Returns at most `limit` features. Returns an empty list on any error
    so a single provider failure does not abort the full signal fetch.
    """
    try:
        r = await client.get(USGS_FEED)
        r.raise_for_status()
        data = r.json()
        return data.get("features", [])[:limit]
    except Exception:
        return []
