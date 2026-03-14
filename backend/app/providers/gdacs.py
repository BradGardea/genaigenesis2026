"""GDACS global disaster event provider.

Fetches active global disaster event features from the GDACS REST API.
Normalization is handled by the service/normalization layer.
"""

from typing import Any
import httpx

from app.core.constants import GDACS_EVENTS_URL


async def fetch_raw_events(
    client: httpx.AsyncClient, limit: int = 10
) -> list[dict[str, Any]]:
    """Fetch raw disaster event features from GDACS.

    Returns at most `limit` features. Returns an empty list on any error.
    """
    try:
        r = await client.get(GDACS_EVENTS_URL)
        r.raise_for_status()
        data = r.json()
        return data.get("features", [])[:limit]
    except Exception:
        return []
