"""Display datetimes in America/Los_Angeles (UTC storage assumed if naive)."""

from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo

    _PACIFIC = ZoneInfo("America/Los_Angeles")
    _USE_PYTZ = False
except Exception:  # ZoneInfoNotFoundError if tzdata missing; older Python
    import pytz

    _PACIFIC = pytz.timezone("America/Los_Angeles")
    _UTC = pytz.UTC
    _USE_PYTZ = True


def to_pacific(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if _USE_PYTZ:
        if dt.tzinfo is None:
            dt = _UTC.localize(dt)
        else:
            dt = dt.astimezone(_UTC)
        return dt.astimezone(_PACIFIC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.astimezone(_PACIFIC)


def pacific_strftime(dt: datetime | None, fmt: str) -> str:
    if dt is None:
        return ""
    p = to_pacific(dt)
    return p.strftime(fmt)
