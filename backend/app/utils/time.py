"""UTC datetime helpers for consistent timestamp formatting across the app."""

from datetime import datetime, timezone, timedelta


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def hours_from_now_iso(hours: int) -> str:
    """Return an ISO 8601 string for a time N hours from now (UTC)."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
