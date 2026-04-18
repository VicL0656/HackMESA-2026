"""Search U.S. places (Nominatim) for home-gym city autocomplete — coordinates used server-side only."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


def search_us_places(
    query: str,
    *,
    user_agent: str,
    limit: int = 12,
    timeout_sec: float = 12.0,
) -> list[dict]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    params = urllib.parse.urlencode(
        {
            "q": f"{q}, USA",
            "format": "json",
            "limit": min(max(limit, 1), 25),
            "countrycodes": "us",
            "addressdetails": 1,
        }
    )
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for row in data:
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        disp = row.get("display_name") or ""
        addr = row.get("address") or {}
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or ""
        state = addr.get("state") or ""
        label = ", ".join(x for x in (city or disp.split(",")[0].strip(), state) if x) or disp[:120]
        out.append({"label": label[:200], "display": disp[:240], "latitude": lat, "longitude": lon})
    return out
