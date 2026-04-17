import math

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from extensions import db
from models import CheckIn, Gym, User, utcnow

bp = Blueprint("gym", __name__, url_prefix="/gym")


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_gym(lat: float, lng: float, max_meters: float = 500.0):
    best = None
    best_d = None
    for gym in Gym.query.all():
        d = haversine_meters(lat, lng, gym.latitude, gym.longitude)
        if best_d is None or d < best_d:
            best_d = d
            best = gym
    if best is None or best_d > max_meters:
        return None, best_d
    return best, best_d


@bp.post("/checkin")
@login_required
def checkin():
    data = request.get_json(silent=True) or {}
    try:
        lat = float(data.get("latitude"))
        lng = float(data.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "latitude and longitude are required as numbers"}), 400

    gym, distance = nearest_gym(lat, lng)
    if gym is None:
        return jsonify(
            {
                "ok": False,
                "error": "No gym found within 500 meters of your location.",
                "nearest_meters": round(distance or 0, 1),
            }
        ), 400

    now = utcnow()
    for row in CheckIn.query.filter_by(user_id=current_user.id, checked_out_at=None).all():
        row.checked_out_at = now

    ci = CheckIn(user_id=current_user.id, gym_id=gym.id, checked_in_at=now, checked_out_at=None)
    db.session.add(ci)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "gym": {
                "id": gym.id,
                "name": gym.name,
                "address": gym.address,
            },
            "distance_meters": round(distance, 1),
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
