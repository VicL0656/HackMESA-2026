"""Persist OpenStreetMap gym candidates as `Gym` rows (shared by check-in and account search)."""

from __future__ import annotations

from extensions import db
from models import Gym


def get_or_create_osm_gym(entry: dict) -> Gym:
    key = (entry.get("osm_key") or "")[:32]
    existing = Gym.query.filter_by(osm_key=key).first() if key else None
    if existing:
        return existing
    g = Gym(
        name=str(entry.get("name") or "Fitness facility")[:200],
        address=str(entry.get("address") or "OpenStreetMap")[:300],
        latitude=float(entry["latitude"]),
        longitude=float(entry["longitude"]),
        osm_key=key or None,
    )
    db.session.add(g)
    db.session.flush()
    return g
