"""NHC (National Hurricane Center) tropical storm provider.

Currently a minimal implementation that fetches the NHC CurrentStorms JSON.
In production, extend this to parse full advisory GeoJSON or RSS feeds for
track, intensity, and wind radii data.
"""

import httpx

from app.core.constants import NHC_ACTIVE_STORMS_URL


async def fetch_active_storms(client: httpx.AsyncClient) -> list[dict]:
    """Fetch active tropical storm summaries from NHC.

    The NHC CurrentStorms.json returns a dict keyed by storm ID.
    Returns a list of storm dicts, or an empty list on any error.

    TODO: Parse full advisory GeoJSON for track / cone of uncertainty.
    """
    try:
        r = await client.get(NHC_ACTIVE_STORMS_URL)
        r.raise_for_status()
        data = r.json()
        # CurrentStorms.json structure varies; values are storm objects
        return list(data.values()) if isinstance(data, dict) else []
    except Exception:
        return []
