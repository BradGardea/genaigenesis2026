"""IBTrACS (International Best Track Archive for Climate Stewardship) provider.

IBTrACS is the authoritative historical tropical cyclone best-track dataset
maintained by NOAA NCEI. It is updated weekly and covers all basins globally.

Use cases in this codebase:
  - Historical track lookup for a named/ID'd storm
  - Seasonal climatology context

Current status: STUB — interface is defined; CSV parsing is not yet implemented.
The IBTrACS CSV file is ~10 MB and requires streaming + filtering; integrating
it properly is deferred to a follow-up sprint.

TODO (production implementation):
  1. Stream the last-3-years CSV from IBTRACS_LAST3_CSV_URL.
  2. Filter rows by SID (storm season ID) matching the requested storm ID.
  3. Convert rows to StormTrackPoint objects via storm_normalization helpers.
  4. Cache the parsed CSV in memory (or a lightweight SQLite store) with a
     weekly TTL to avoid re-downloading on every request.
  5. Index by season (YEAR) and basin for fast lookup.

IBTrACS CSV key columns:
  SID, SEASON, NUMBER, BASIN, NAME, ISO_TIME, LAT, LON,
  WMO_WIND (kt), WMO_PRES (mb), NATURE (classification)
"""

from __future__ import annotations

import httpx

from app.core.constants import IBTRACS_LAST3_CSV_URL  # noqa: F401 (used by TODO impl)


async def fetch_historical_track(
    client: httpx.AsyncClient,  # noqa: ARG001
    storm_id: str,  # noqa: ARG001
) -> list[dict]:
    """Return historical best-track points for a storm from IBTrACS.

    Args:
        client: Shared async HTTP client.
        storm_id: IBTrACS SID or NHC-style ID (e.g. 'al012005' for Katrina).

    Returns:
        List of raw track-point dicts compatible with
        storm_normalization.nhc_raw_track_to_points().
        Currently always returns an empty list (not yet implemented).
    """
    # TODO: Implement CSV download, filtering by storm_id, and row → dict mapping.
    # See module docstring for column reference.
    return []
