from __future__ import annotations

import math

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from extensions import db
from models import CheckIn, Gym, User, utcnow
from osm_gyms import discover_gyms_nearby

bp = Blueprint("gym", __name__, url_prefix="/gym")

_METERS_PER_MILE = 1609.344


def _miles_from_meters(m: float) -> float:
    return m / _METERS_PER_MILE


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))


def active_check_in(user_id: int) -> CheckIn | None:
    return (
        CheckIn.query.filter_by(user_id=user_id, checked_out_at=None)
        .order_by(CheckIn.checked_in_at.desc())
        .first()
    )


def nearest_gym(lat: float, lng: float, max_meters: float):
    gyms = Gym.query.order_by(Gym.id).all()
    if not gyms:
        return None, None, None

    best: Gym | None = None
    best_d: float | None = None
    for gym in gyms:
        try:
            glat = float(gym.latitude)
            glng = float(gym.longitude)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(glat) or not math.isfinite(glng) or abs(glat) > 90 or abs(glng) > 180:
            continue
        d = haversine_meters(lat, lng, glat, glng)
        if best_d is None or d < best_d:
            best_d = d
            best = gym

    if best is None or best_d is None:
        return None, None, None
    if best_d > max_meters:
        return None, best_d, best
    return best, best_d, best


def _get_or_create_osm_gym(entry: dict) -> Gym:
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


@bp.post("/checkin")
@login_required
def checkin():
    data = request.get_json(silent=True) or {}
    try:
        lat = float(data.get("latitude"))
        lng = float(data.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "latitude and longitude are required as numbers"}), 400

    if not math.isfinite(lat) or not math.isfinite(lng) or abs(lat) > 90 or abs(lng) > 180:
        return jsonify({"ok": False, "error": "latitude and longitude are out of range"}), 400

    max_m = float(current_app.config.get("GYM_CHECKIN_MAX_METERS", 25 * _METERS_PER_MILE))
    max_mi = float(current_app.config.get("GYM_CHECKIN_MAX_MILES", _miles_from_meters(max_m)))
    gym, distance, nearest = nearest_gym(lat, lng, max_meters=max_m)

    if gym is None:
        overpass_url = str(current_app.config.get("OVERPASS_API_URL"))
        ua = str(current_app.config.get("GYMLINK_HTTP_USER_AGENT"))
        osm_candidates = discover_gyms_nearby(
            lat, lng, max_m, overpass_url=overpass_url, user_agent=ua
        )
        best_entry = None
        best_d_osm: float | None = None
        for entry in osm_candidates:
            d = haversine_meters(lat, lng, float(entry["latitude"]), float(entry["longitude"]))
            if d <= max_m and (best_d_osm is None or d < best_d_osm):
                best_d_osm = d
                best_entry = entry
        if best_entry is not None and best_d_osm is not None:
            gym = _get_or_create_osm_gym(best_entry)
            distance = best_d_osm

    if gym is None:
        err_parts = [
            f"No gym or fitness centre found within {max_mi:.1f} miles of your location "
            f"(using OpenStreetMap near your GPS coordinates)."
        ]
        if nearest is not None and distance is not None:
            err_parts.append(
                f"The nearest gym already saved in GymLink is about {_miles_from_meters(distance):.1f} mi away ({nearest.name})."
            )
        payload: dict = {
            "ok": False,
            "error": " ".join(err_parts),
            "max_meters": max_m,
            "max_miles": round(max_mi, 2),
        }
        if nearest is not None and distance is not None:
            payload["nearest_meters"] = round(distance, 1)
            payload["nearest_miles"] = round(_miles_from_meters(distance), 2)
            payload["nearest_gym"] = {
                "name": nearest.name,
                "address": nearest.address,
                "latitude": nearest.latitude,
                "longitude": nearest.longitude,
            }
        payload["hint"] = (
            "GymLink looks up tagged fitness centres and gyms in OpenStreetMap. "
            "If your area is sparse, try again outdoors, increase GYM_CHECKIN_MAX_MILES, "
            "or add missing venues in OpenStreetMap."
        )
        return jsonify(payload), 400

    now = utcnow()
    for row in CheckIn.query.filter_by(user_id=current_user.id, checked_out_at=None).all():
        row.checked_out_at = now

    ci = CheckIn(user_id=current_user.id, gym_id=gym.id, checked_in_at=now, checked_out_at=None)
    db.session.add(ci)
    db.session.commit()

    dist = float(distance or 0)
    return jsonify(
        {
            "ok": True,
            "gym": {
                "id": gym.id,
                "name": gym.name,
                "address": gym.address,
            },
            "source": "openstreetmap" if gym.osm_key else "saved",
            "distance_meters": round(dist, 1),
            "distance_miles": round(_miles_from_meters(dist), 2),
            "max_meters": max_m,
            "max_miles": round(max_mi, 2),
        }
    )


@bp.post("/checkout")
@login_required
def checkout():
    rows = CheckIn.query.filter_by(user_id=current_user.id, checked_out_at=None).all()
    if not rows:
        return jsonify({"ok": True, "message": "You were not checked in."})

    now = utcnow()
    for row in rows:
        row.checked_out_at = now
    db.session.commit()
    return jsonify({"ok": True})


@bp.get("/feed")
@login_required
def gym_feed_json():
    ci = active_check_in(current_user.id)
    if not ci:
        return jsonify({"ok": True, "checked_in": False, "users": []})

    others = (
        db.session.query(User, CheckIn)
        .join(CheckIn, CheckIn.user_id == User.id)
        .filter(
            CheckIn.gym_id == ci.gym_id,
            CheckIn.checked_out_at.is_(None),
            User.id != current_user.id,
        )
        .all()
    )
    users_out = [
        {
            "id": u.id,
            "name": u.name,
            "username": u.username,
            "photo_url": u.photo_url,
            "workout_style": u.workout_style,
            "checked_in_at": c.checked_in_at.isoformat(),
        }
        for u, c in others
    ]
    return jsonify(
        {
            "ok": True,
            "checked_in": True,
            "gym": {"id": ci.gym.id, "name": ci.gym.name},
            "users": users_out,
        }
    )
