"""Geocode a free-text city/area query (Nominatim) for gym search."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


def geocode_city(
    query: str,
    *,
    user_agent: str,
    timeout_sec: float = 12.0,
) -> tuple[float, float] | None:
    q = (query or "").strip()
    if len(q) < 2:
        return None
    params = urllib.parse.urlencode(
        {
            "q": q,
            "format": "json",
            "limit": 1,
        }
    )
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return None
    if not data:
        return None
    row = data[0]
    try:
        lat = float(row["lat"])
        lon = float(row["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return lat, lon
