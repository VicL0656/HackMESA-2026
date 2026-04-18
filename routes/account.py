"""Account owner-only settings (email is never shown on public profile)."""

from __future__ import annotations

import json
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Gym

bp = Blueprint("account", __name__, url_prefix="/account")

_EDU = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu$")


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
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

    gyms = Gym.query.order_by(Gym.name).limit(500).all()
    wd_raw = getattr(current_user, "workout_days", None) or "[]"
    try:
        workout_day_set = {int(x) for x in json.loads(wd_raw)}
    except (json.JSONDecodeError, TypeError, ValueError):
        workout_day_set = set()
    return render_template(
        "account_settings.html",
        gyms=gyms,
        workout_day_set=workout_day_set,
    )
