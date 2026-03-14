"""NOAA / USGS Water Services streamflow provider.

Currently a minimal placeholder for integrating streamflow and flood-stage
data from the USGS Instantaneous Values web service (NWIS).

In production, use site codes from the USGS site service to query
streamflow (parameterCd=00060) or gauge height (parameterCd=00065) for
specific stations near a location of interest.
"""

import httpx

from app.core.constants import NOAA_WATER_SERVICES_URL


async def fetch_streamflow(
    client: httpx.AsyncClient,
    site: str | None = None,
) -> dict:
    """Fetch instantaneous streamflow data for a USGS gauge site.

    Args:
        site: USGS site code (e.g. "01646500" for Potomac at Little Falls).
              Returns empty dict if not provided.

    Returns:
        Raw NWIS JSON response dict, or empty dict on error or missing site.

    TODO: Add site discovery by lat/lon bounding box using the USGS site service.
    """
    if not site:
        return {}
    params = {"sites": site, "format": "json", "parameterCd": "00060"}
    try:
        r = await client.get(NOAA_WATER_SERVICES_URL, params=params)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}
