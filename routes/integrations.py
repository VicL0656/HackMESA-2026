"""
Bridge for Apple Health / Shortcuts / other clients that can send HTTP.

Safari cannot read HealthKit. Typical flow: iOS Shortcut (optionally fed by
Health samples or an Automation) POSTs JSON to /api/integrations/workout
with Authorization: Bearer <token> from GymLink Settings.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from extensions import db
from health_bridge_auth import hash_health_bridge_token
from models import User, WeightLog, Workout
from models import utcnow
from realtime import emit_leaderboard_refresh
from routes.workouts import _apply_pr, _update_streak_for_log

bp = Blueprint("integrations", __name__, url_prefix="/api/integrations")


def _user_from_bridge_token() -> User | None:
    auth = (request.headers.get("Authorization") or "").strip()
    token: str | None = None
    low = auth.lower()
    if low.startswith("bearer "):
        token = auth[7:].strip()
    elif low.startswith("token "):
        token = auth[6:].strip()
    if not token:
        return None
    secret = current_app.config.get("SECRET_KEY") or ""
    th = hash_health_bridge_token(secret, token)
    return User.query.filter_by(health_bridge_token_hash=th).first()


@bp.post("/workout")
def bridge_workout():
    user = _user_from_bridge_token()
    if not user:
        return jsonify({"ok": False, "error": "Missing or invalid token. Use Authorization: Bearer <token> from Settings → Apple Health & Shortcuts."}), 401

    data = request.get_json(silent=True) or {}
    exercise_name = (data.get("exercise_name") or data.get("exercise") or "").strip()
    try:
        weight_lbs = float(data.get("weight_lbs"))
        reps = int(data.get("reps"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "weight_lbs (number) and reps (integer) are required."}), 400

    if not exercise_name:
        return jsonify({"ok": False, "error": "exercise_name is required."}), 400
    if weight_lbs < 0 or reps < 1:
        return jsonify({"ok": False, "error": "Invalid weight or reps."}), 400

    caption = (data.get("caption") or "").strip() or None
    logged_at = utcnow()
    raw_la = data.get("logged_at")
    if raw_la:
        try:
            raw = str(raw_la).replace("Z", "+00:00")
            logged_at = datetime.fromisoformat(raw)
            if logged_at.tzinfo is None:
                logged_at = logged_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass

    workout = Workout(
        user_id=user.id,
        exercise_name=exercise_name[:120],
        weight_lbs=weight_lbs,
        reps=reps,
        logged_at=logged_at,
        caption=caption,
        photo_path=None,
        is_pr_session=False,
        is_rest_day=False,
    )
    db.session.add(workout)
    db.session.flush()

    is_pr = _apply_pr(user.id, exercise_name, weight_lbs, reps)
    workout.is_pr_session = bool(is_pr)
    _update_streak_for_log(user.id)
    db.session.commit()

    emit_leaderboard_refresh(user.id)

    if is_pr:
        from notification_helpers import notify_friends_of_pr

        notify_friends_of_pr(user, workout, exercise_name, weight_lbs, reps)
        db.session.commit()

    return jsonify(
        {
            "ok": True,
            "workout_id": workout.id,
            "is_pr": bool(is_pr),
            "exercise_name": exercise_name,
        }
    )


@bp.post("/body-weight")
def bridge_body_weight():
    user = _user_from_bridge_token()
    if not user:
        return jsonify({"ok": False, "error": "Missing or invalid token."}), 401

    data = request.get_json(silent=True) or {}
    try:
        w = float(data.get("weight_lbs"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "weight_lbs required as a number."}), 400
    if w <= 20 or w > 1000:
        return jsonify({"ok": False, "error": "Weight out of plausible range."}), 400

    vis = (data.get("visibility") or "private").strip().lower()
    if vis not in ("public", "friends", "private"):
        vis = "private"

    db.session.add(WeightLog(user_id=user.id, weight_lbs=w, logged_at=utcnow(), visibility=vis))
    db.session.commit()
    return jsonify({"ok": True})
