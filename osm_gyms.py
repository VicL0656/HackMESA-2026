"""
Find fitness facilities near the user via OpenStreetMap (Overpass API).
Data © OpenStreetMap contributors — https://www.openstreetmap.org/copyright
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Any


def _addr_from_tags(tags: dict[str, str]) -> str:
    if not tags:
        return ""
    full = (tags.get("addr:full") or "").strip()
    if full:
        return full[:299]
    parts: list[str] = []
    hn = (tags.get("addr:housenumber") or "").strip()
    st = (tags.get("addr:street") or "").strip()
    if hn and st:
        parts.append(f"{hn} {st}")
    elif st:
        parts.append(st)
    for key in ("addr:city", "addr:state", "addr:postcode"):
        v = (tags.get(key) or "").strip()
        if v:
            parts.append(v)
    return ", ".join(parts)[:299] if parts else ""


def _element_coords(el: dict[str, Any]) -> tuple[float, float] | None:
    if el.get("type") == "node" and "lat" in el and "lon" in el:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def _element_osm_key(el: dict[str, Any]) -> str | None:
    t = el.get("type")
    eid = el.get("id")
    if t not in ("node", "way", "relation") or eid is None:
        return None
    return f"{str(t)[0]}/{int(eid)}"


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))


def discover_gyms_nearby(
    lat: float,
    lng: float,
    radius_m: float,
    *,
    overpass_url: str,
    user_agent: str,
    timeout_sec: float = 28.0,
) -> list[dict[str, Any]]:
    """
    Return OSM-backed gym candidates within radius_m (Haversine filtering on OSM bbox is approximate).
    Each dict: osm_key, name, address, latitude, longitude.
    """
    if not math.isfinite(lat) or not math.isfinite(lng) or abs(lat) > 90 or abs(lng) > 180:
        return []
    r = max(100, min(int(radius_m), 50000))
    # Overpass `around` uses meters from lat/lng.
    q = f"""[out:json][timeout:25];
(
  node(around:{r},{lat},{lng})["leisure"="fitness_centre"];
  way(around:{r},{lat},{lng})["leisure"="fitness_centre"];
  node(around:{r},{lat},{lng})["amenity"="gym"];
  way(around:{r},{lat},{lng})["amenity"="gym"];
);
out center tags;"""

    req = urllib.request.Request(
        overpass_url,
        data=q.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": user_agent,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    elements = data.get("elements")
    if not isinstance(elements, list):
        return []

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        key = _element_osm_key(el)
        if not key or key in seen:
            continue
        coords = _element_coords(el)
        if coords is None:
            continue
        tags = el.get("tags") or {}
        if not isinstance(tags, dict):
            tags = {}
        stags = {str(k): str(v) for k, v in tags.items() if v is not None}
        name = (stags.get("name") or stags.get("operator") or "").strip()
        if not name:
            name = "Fitness facility"
        addr = _addr_from_tags(stags) or "Address from OpenStreetMap"
        seen.add(key)
        out.append(
            {
                "osm_key": key,
                "name": name[:200],
                "address": addr[:300] if addr else "OpenStreetMap",
                "latitude": coords[0],
                "longitude": coords[1],
            }
        )
    out.sort(key=lambda e: _haversine_meters(lat, lng, e["latitude"], e["longitude"]))
    return out[:300]
