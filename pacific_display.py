"""Display datetimes in America/Los_Angeles (UTC storage assumed if naive)."""

from __future__ import annotations

from datetime import date, datetime

import pytz

PACIFIC_TZ = pytz.timezone("America/Los_Angeles")
UTC = pytz.UTC


def to_pacific(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    else:
        dt = dt.astimezone(UTC)
    return dt.astimezone(PACIFIC_TZ)


def pacific_strftime(dt: datetime | None, fmt: str) -> str:
    if dt is None:
        return ""
    p = to_pacific(dt)
    return p.strftime(fmt)
