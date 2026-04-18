"""Account settings: profile, password, training prefs, home gym search."""

from __future__ import annotations

import json
import math
import re

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

from extensions import bcrypt, db
from geocode import geocode_city
from gym_store import get_or_create_osm_gym
from models import Gym
from osm_gyms import discover_gyms_nearby
from tom_friend import is_reserved_username, is_tom_user
from username_utils import USERNAME_RE, find_user_by_username_ci, normalize_username

bp = Blueprint("account", __name__, url_prefix="/account")

_EDU = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu$")


def _settings_context():
    gyms = Gym.query.order_by(Gym.name).limit(500).all()
    wd_raw = getattr(current_user, "workout_days", None) or "[]"
    try:
        workout_day_set = {int(x) for x in json.loads(wd_raw)}
    except (json.JSONDecodeError, TypeError, ValueError):
        workout_day_set = set()
    return {
        "gyms": gyms,
        "workout_day_set": workout_day_set,
        "show_delete_account": not is_tom_user(current_user),
    }


def _settings_render():
    return render_template("account_settings.html", **_settings_context())


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        part = (request.form.get("form_part") or "training").strip()

        if part == "profile":
            name = (request.form.get("name") or "").strip()
            username_raw = (request.form.get("username") or "").strip()
            username = normalize_username(username_raw)
            if not name:
                flash("Display name is required.", "error")
                return redirect(url_for("account.settings"))
            if not username or not USERNAME_RE.match(username):
                flash(
                    "Username must be 3–30 characters: letters, numbers, underscores (any letter case).",
                    "error",
                )
                return redirect(url_for("account.settings"))
            clash_row = find_user_by_username_ci(username)
            clash = clash_row if clash_row and clash_row.id != current_user.id else None
            if clash:
                flash("That username is already taken.", "error")
                return redirect(url_for("account.settings"))
            if is_reserved_username(username):
                flash("That username is reserved for the default friend account.", "error")
                return redirect(url_for("account.settings"))
            current_user.name = name[:120]
            current_user.username = username
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("account.settings"))

        if part == "password":
            old_pw = request.form.get("current_password") or ""
            new_pw = request.form.get("new_password") or ""
            new2 = request.form.get("new_password_confirm") or ""
            if len(new_pw) < 8:
                flash("New password must be at least 8 characters.", "error")
                return redirect(url_for("account.settings"))
            if new_pw != new2:
                flash("New passwords do not match.", "error")
                return redirect(url_for("account.settings"))
            if not bcrypt.check_password_hash(current_user.password_hash, old_pw):
                flash("Current password is incorrect.", "error")
                return redirect(url_for("account.settings"))
            h = bcrypt.generate_password_hash(new_pw)
            if isinstance(h, bytes):
                h = h.decode("utf-8")
            current_user.password_hash = h
            db.session.commit()
            flash("Password updated.", "success")
            return redirect(url_for("account.settings"))

        if part == "privacy":
            current_user.public_show_streak_stats = bool(request.form.get("public_show_streak_stats"))
            current_user.public_show_pr_highlights = bool(request.form.get("public_show_pr_highlights"))
            current_user.public_show_profile_fields = bool(request.form.get("public_show_profile_fields"))
            current_user.public_weight_chart = bool(request.form.get("public_weight_chart"))
            current_user.public_workout_progress = bool(request.form.get("public_workout_progress"))
            db.session.commit()
            flash("Privacy settings saved.", "success")
            return redirect(url_for("account.settings") + "#privacy")

        # training (default)
        if part != "training":
            flash("Could not save that section.", "error")
            return redirect(url_for("account.settings"))

        current_user.goal_weight_lbs = None
        gw = (request.form.get("goal_weight_lbs") or "").strip()
        if gw:
            try:
                current_user.goal_weight_lbs = float(gw)
            except ValueError:
                flash("Goal weight must be a number.", "error")
                return redirect(url_for("account.settings"))
        hg = request.form.get("home_gym_id", type=int)
        current_user.home_gym_id = hg if hg else None
        days = request.form.getlist("workout_day")
        ints: list[int] = []
        for d in days:
            try:
                v = int(d)
                if 0 <= v <= 6:
                    ints.append(v)
            except ValueError:
                pass
        current_user.workout_days = json.dumps(sorted(set(ints)))

        try:
            rh = int(request.form.get("reminder_hour") or 8)
            rm = int(request.form.get("reminder_minute") or 0)
        except (TypeError, ValueError):
            rh, rm = 8, 0
        current_user.reminder_hour = max(0, min(23, rh))
        current_user.reminder_minute = max(0, min(59, rm))

        raw_se = (request.form.get("school_email") or "").strip().lower()
        if raw_se:
            if not _EDU.match(raw_se):
                flash("School email must be a valid .edu address.", "error")
                return redirect(url_for("account.settings"))
            current_user.school_email = raw_se
        else:
            current_user.school_email = None

        db.session.commit()
        flash("Training preferences saved.", "success")
        return redirect(url_for("account.settings"))

    return _settings_render()


@bp.post("/api/city-search")
@login_required
def api_city_search():
    from city_search import search_us_places

    data = request.get_json(silent=True) or {}
    q = (data.get("query") or "").strip()
    if len(q) < 2:
        return jsonify({"ok": False, "error": "Type at least two characters."}), 400
    ua = str(current_app.config.get("GYMLINK_HTTP_USER_AGENT", "GymLink/1.0"))
    rows = search_us_places(q, user_agent=ua, limit=15)
    return jsonify({"ok": True, "places": rows})


@bp.post("/api/gym-search")
@login_required
def api_gym_search():
    """Geocode a city/area, then return nearby gyms from OSM (saved to DB on pick)."""
    data = request.get_json(silent=True) or {}
    q = (data.get("query") or data.get("city") or "").strip()
    ua = str(current_app.config.get("GYMLINK_HTTP_USER_AGENT", "GymLink/1.0"))
    lat = data.get("latitude")
    lng = data.get("longitude")
    if lat is not None and lng is not None:
        try:
            lat_f = float(lat)
            lon_f = float(lng)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid coordinates."}), 400
        if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
            return jsonify({"ok": False, "error": "Invalid coordinates."}), 400
        lat, lon = lat_f, lon_f
    else:
        if len(q) < 2:
            return jsonify({"ok": False, "error": "Enter a city or neighborhood."}), 400
        coords = geocode_city(q, user_agent=ua)
        if not coords:
            return jsonify({"ok": False, "error": "Could not find that location. Try a larger nearby city."}), 400
        lat, lon = coords
    overpass_url = str(current_app.config.get("OVERPASS_API_URL"))
    radius = min(float(data.get("radius_m") or 25000), 50000)
    raw = discover_gyms_nearby(lat, lon, radius, overpass_url=overpass_url, user_agent=ua)
    out: list[dict] = []
    seen: set[str] = set()
    for entry in raw[:40]:
        key = (entry.get("osm_key") or "")[:32]
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        glat = float(entry["latitude"])
        glng = float(entry["longitude"])
        d = _haversine_meters(lat, lon, glat, glng)
        row = Gym.query.filter_by(osm_key=key).first() if key else None
        out.append(
            {
                "id": row.id if row else None,
                "osm_key": key or None,
                "name": str(entry.get("name") or "Gym")[:200],
                "address": str(entry.get("address") or "")[:300],
                "latitude": glat,
                "longitude": glng,
                "distance_m": round(d, 0),
            }
        )
    return jsonify({"ok": True, "center": {"lat": lat, "lon": lon}, "gyms": out})


@bp.post("/api/gym-pick")
@login_required
def api_gym_pick():
    data = request.get_json(silent=True) or {}
    gym_id = data.get("gym_id")
    entry = data.get("entry")
    if gym_id is not None:
        try:
            gid = int(gym_id)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid gym id."}), 400
        g = db.session.get(Gym, gid)
        if not g:
            return jsonify({"ok": False, "error": "Gym not found."}), 404
        current_user.home_gym_id = g.id
        db.session.commit()
        return jsonify({"ok": True, "gym": {"id": g.id, "name": g.name}})
    if isinstance(entry, dict) and entry.get("latitude") is not None:
        g = get_or_create_osm_gym(entry)
        current_user.home_gym_id = g.id
        db.session.commit()
        return jsonify({"ok": True, "gym": {"id": g.id, "name": g.name}})
    return jsonify({"ok": False, "error": "Provide gym_id or entry."}), 400


@bp.post("/api/gym-manual")
@login_required
def api_gym_manual():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    address = (data.get("address") or "").strip() or "Custom"
    if not name:
        return jsonify({"ok": False, "error": "Gym name is required."}), 400
    lat_raw = data.get("latitude")
    lng_raw = data.get("longitude")
    lat: float
    lng: float
    if lat_raw is not None and lng_raw is not None:
        try:
            lat = float(lat_raw)
            lng = float(lng_raw)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid coordinates."}), 400
    else:
        ua = str(current_app.config.get("GYMLINK_HTTP_USER_AGENT", "GymLink/1.0"))
        geo_q = f"{name}, {address}, USA".strip()
        coords = geocode_city(geo_q, user_agent=ua)
        if not coords:
            return jsonify(
                {"ok": False, "error": "Could not find that location. Include city and state in the address line."}
            ), 400
        lat, lng = coords
    if not math.isfinite(lat) or not math.isfinite(lng) or abs(lat) > 90 or abs(lng) > 180:
        return jsonify({"ok": False, "error": "Invalid coordinates."}), 400
    g = Gym(
        name=name[:200],
        address=address[:300],
        latitude=lat,
        longitude=lng,
        osm_key=None,
    )
    db.session.add(g)
    db.session.flush()
    current_user.home_gym_id = g.id
    db.session.commit()
    return jsonify({"ok": True, "gym": {"id": g.id, "name": g.name}})


@bp.post("/delete-account")
@login_required
def delete_account():
    if is_tom_user(current_user):
        abort(403)
    pw = request.form.get("password") or ""
    confirm = (request.form.get("delete_confirm") or "").strip()
    if confirm != "DELETE MY ACCOUNT":
        flash("Type DELETE MY ACCOUNT in the confirmation box to delete your account.", "error")
        return redirect(url_for("account.settings") + "#delete-account")
    if not bcrypt.check_password_hash(current_user.password_hash, pw):
        flash("Password is incorrect.", "error")
        return redirect(url_for("account.settings") + "#delete-account")

    from user_delete import delete_user_account

    uid = current_user.id
    logout_user()
    delete_user_account(uid)
    db.session.commit()
    flash("Your account has been deleted.", "info")
    return redirect(url_for("auth.login"))
