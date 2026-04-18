"""Body weight log + chart."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import WeightLog
from models import utcnow

bp = Blueprint("weights", __name__, url_prefix="/weights")


@bp.route("/log", methods=["GET", "POST"])
@login_required
def weight_log():
    if request.method == "POST":
        vis = (request.form.get("visibility") or "friends").strip().lower()
        if vis not in ("public", "friends", "private"):
            vis = "friends"
        try:
            w = float(request.form.get("weight_lbs") or "")
        except (TypeError, ValueError):
            flash("Enter a valid weight.", "error")
            return redirect(url_for("weights.weight_log"))
        if w <= 20 or w > 1000:
            flash("Weight looks out of range.", "error")
            return redirect(url_for("weights.weight_log"))
        db.session.add(
            WeightLog(user_id=current_user.id, weight_lbs=w, logged_at=utcnow(), visibility=vis)
        )
        db.session.commit()
        flash("Weight logged.", "success")
        return redirect(url_for("weights.weight_log"))

    logs = (
        WeightLog.query.filter_by(user_id=current_user.id)
        .order_by(WeightLog.logged_at.asc())
        .all()
    )
    chart_labels = [l.logged_at.date().isoformat() for l in logs]
    chart_data = [round(l.weight_lbs, 1) for l in logs]
    return render_template(
        "weight_log.html",
        logs=logs,
        chart_labels=chart_labels,
        chart_data=chart_data,
    )


@bp.post("/log/<int:log_id>/delete")
@login_required
def weight_delete(log_id: int):
    row = WeightLog.query.filter_by(id=log_id, user_id=current_user.id).first()
    if row:
        db.session.delete(row)
        db.session.commit()
        flash("Entry removed.", "info")
    return redirect(url_for("weights.weight_log"))
