"""NHC (National Hurricane Center) tropical storm provider.

Fetches active tropical cyclone data from the NHC public JSON feeds.

Advisory GeoJSON products (5-day cone, track, wind radii) are fetched
from the NHC storm_graphics API when available; they fall back to None
gracefully if the storm is not active or the endpoint returns non-200.

TODO (production hardening):
  - Subscribe to NHC RSS/ATOM advisory feeds for push-based updates.
  - Parse the NHC GIS ZIP products (shapefiles) for higher-fidelity geometry.
  - Add ETag/Last-Modified caching to reduce polling load on NHC servers.
"""

import httpx

from app.core.constants import NHC_ACTIVE_STORMS_URL, NHC_ADVISORY_GEOJSON_BASE


async def fetch_active_storms(client: httpx.AsyncClient) -> list[dict]:
    """Fetch active tropical storm summaries from NHC CurrentStorms.json.

    The NHC CurrentStorms.json may be either:
      - A dict keyed by storm ID: {"al012025": {...}, ...}
      - A dict with an "activeStorms" list: {"activeStorms": [...]}

    Returns a list of raw storm dicts, or an empty list on any error.
    """
    try:
        r = await client.get(NHC_ACTIVE_STORMS_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return []
        # Handle {"activeStorms": [...]} shape
        if "activeStorms" in data and isinstance(data["activeStorms"], list):
            return data["activeStorms"]
        # Handle flat keyed dict {"al012025": {...}, ...}
        # Filter out non-dict values to avoid parsing metadata keys
        return [v for v in data.values() if isinstance(v, dict)]
    except Exception:
        return []


async def fetch_storm_by_id(client: httpx.AsyncClient, storm_id: str) -> dict | None:
    """Return a single storm dict from the CurrentStorms feed by storm ID.

    Storm IDs are matched case-insensitively (e.g. 'al012025' == 'AL012025').
    Returns None if the storm is not currently active.
    """
    storms = await fetch_active_storms(client)
    needle = storm_id.lower()
    for s in storms:
        sid = str(s.get("id") or s.get("stormId") or "").lower()
        if sid == needle:
            return s
    return None


async def fetch_advisory_geojson(
    client: httpx.AsyncClient, storm_id: str
) -> dict | None:
    """Attempt to fetch the NHC 5-day advisory GeoJSON for a specific storm.

    NHC advisory GeoJSON URL format:
        {NHC_ADVISORY_GEOJSON_BASE}/{STORM_ID_UPPER}_5day_latest.json

    Returns the parsed JSON dict on success, or None if the endpoint
    returns a non-200 status or is unavailable.

    NOTE: NHC does not guarantee JSON availability for all storms or
    between advisory issuance times. Callers must treat None as normal.
    """
    storm_upper = storm_id.upper()
    url = f"{NHC_ADVISORY_GEOJSON_BASE}/{storm_upper}_5day_latest.json"
    try:
        r = await client.get(url, timeout=15)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None
