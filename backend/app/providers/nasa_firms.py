"""NASA FIRMS fire detection provider.

Fetches thermal anomaly (active fire) CSV data from the FIRMS API.
Requires a valid NASA_FIRMS_KEY environment variable.
"""

import httpx

NASA_FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
DEFAULT_BBOX = "-130,20,-60,55"  # Continental US bounding box


async def fetch_raw_fires(
    client: httpx.AsyncClient,
    api_key: str,
    bbox: str = DEFAULT_BBOX,
    source: str = "VIIRS_SNPP_NRT",
    limit: int = 5,
) -> list[dict[str, float | str]]:
    """Fetch raw fire detection rows from NASA FIRMS.

    Parses the CSV response and returns a list of dicts with 'lat' and 'lon'.
    Returns an empty list if the key is missing or the request fails.
    """
    if not api_key:
        return []
    url = f"{NASA_FIRMS_BASE}/{api_key}/{source}/{bbox}"
    try:
        r = await client.get(url)
        r.raise_for_status()
        rows = r.text.split("\n")[1 : limit + 1]
        results: list[dict[str, float | str]] = []
        for row in rows:
            cols = row.split(",")
            if len(cols) < 2:
                continue
            try:
                results.append({"lat": float(cols[0]), "lon": float(cols[1])})
            except ValueError:
                continue
        return results
    except Exception:
        return []
