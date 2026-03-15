"""JTWC (Joint Typhoon Warning Center) tropical storm provider.

JTWC covers Western Pacific (WP), Indian Ocean (IO), and Southern
Hemisphere (SH) basin storms — complementing NHC's Atlantic/East-Pacific
coverage.

JTWC does not expose a public JSON API. Data is published as:
  - RSS feed  (https://www.metoc.navy.mil/jtwc/rss/jtwc.rss)
  - Plain-text advisory files via FTP
  - HTML product pages

Current implementation: RSS-based listing with plain-text advisory
link extraction. Returns an empty list if the RSS feed is unreachable
so that the storm service can fall back to NHC-only data.

TODO (production hardening):
  - Parse the JTWC best-track text (b-deck) files for accurate track data.
  - Use the NRL Tropical Cyclone Page as an alternative structured source:
    https://www.nrlmry.navy.mil/tcdat/
  - Add XML namespace-aware parsing for the RSS entries.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

from app.core.constants import JTWC_RSS_URL


# ---------------------------------------------------------------------------
# Internal XML helpers
# ---------------------------------------------------------------------------


def _text(element: Optional[ET.Element]) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _parse_rss_entries(xml_bytes: bytes) -> list[dict]:
    """Parse JTWC RSS feed into raw storm-like dicts.

    Each RSS <item> describes one active system advisory. We extract
    title (storm name/ID), description, and the advisory link.

    Example title format: "Tropical Storm 01W (MAWAR)"
    We derive storm ID and name from the title.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    entries: list[dict] = []
    channel = root.find("channel")
    if channel is None:
        return []

    for item in channel.findall("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        description = _text(item.find("description"))

        # Extract basin+number from title: "01W", "02A", "05S" etc.
        storm_id_match = re.search(r"\b(\d{2}[A-Z])\b", title)
        storm_id = storm_id_match.group(1).lower() if storm_id_match else ""

        # Extract storm name from parentheses
        name_match = re.search(r"\(([A-Z]+)\)", title)
        name = name_match.group(1) if name_match else title[:20].upper()

        if not storm_id:
            continue

        entries.append(
            {
                "id": storm_id,
                "name": name,
                "headline": description[:200] if description else "",
                "advisory_url": link,
                "classification": _infer_classification(title),
                # Coordinates are not available in the RSS feed
                "latitude": None,
                "longitude": None,
                "source": "jtwc",
            }
        )
    return entries


def _infer_classification(title: str) -> str:
    """Derive a classification code from a JTWC advisory title string."""
    t = title.lower()
    if "super typhoon" in t:
        return "STY"
    if "typhoon" in t:
        return "TY"
    if "tropical storm" in t:
        return "TS"
    if "tropical depression" in t:
        return "TD"
    if "tropical cyclone" in t:
        return "TC"
    return "INVEST"


# ---------------------------------------------------------------------------
# Public async interface
# ---------------------------------------------------------------------------


async def fetch_active_storms(client: httpx.AsyncClient) -> list[dict]:
    """Fetch active JTWC storms from the JTWC RSS feed.

    Returns a list of raw storm dicts (with minimal fields) or an empty
    list if the feed is unreachable or returns no parseable entries.
    """
    try:
        r = await client.get(JTWC_RSS_URL, timeout=15)
        r.raise_for_status()
        return _parse_rss_entries(r.content)
    except Exception:
        return []
