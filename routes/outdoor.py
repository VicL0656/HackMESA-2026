from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import OutdoorActivity
from models import utcnow
from realtime import emit_leaderboard_refresh
from uploads_util import file_was_chosen, save_uploaded_image

bp = Blueprint("outdoor", __name__, url_prefix="/outdoor")

OUTDOOR_KINDS = ["run", "bike", "hike", "swim", "other"]


@bp.route("/log", methods=["GET", "POST"])
@login_required
def log_outdoor():
    if request.method == "POST":
        kind = (request.form.get("kind") or "").strip().lower()
        title = (request.form.get("title") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None
        score_raw = request.form.get("score")
        score_label = (request.form.get("score_label") or "").strip() or None
        dist_raw = request.form.get("distance_miles")
        dur_raw = request.form.get("duration_minutes")

        if kind not in OUTDOOR_KINDS:
            flash("Pick a valid activity type.", "error")
            return render_template("outdoor_log.html", kinds=OUTDOOR_KINDS)

        if not title:
            flash("Title is required.", "error")
            return render_template("outdoor_log.html", kinds=OUTDOOR_KINDS)

        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            flash("Score must be a number (higher is better for the leaderboard).", "error")
            return render_template("outdoor_log.html", kinds=OUTDOOR_KINDS)

        distance_miles = None
        duration_minutes = None
        if dist_raw:
            try:
                distance_miles = float(dist_raw)
            except ValueError:
                pass
        if dur_raw:
            try:
                duration_minutes = float(dur_raw)
            except ValueError:
                pass

        fphoto = request.files.get("photo")
        photo = save_uploaded_image(fphoto, f"out_{current_user.id}")
        if file_was_chosen(fphoto) and not photo:
            flash(
                "Photo was not saved. Use JPG, PNG, WEBP, or GIF under the 25 MB limit (HEIC/iPhone often needs “Most Compatible”).",
                "warning",
            )
        row = OutdoorActivity(
            user_id=current_user.id,
            kind=kind,
            title=title,
            notes=notes,
            distance_miles=distance_miles,
            duration_minutes=duration_minutes,
            score=score,
            score_label=score_label,
            photo_path=photo,
            posted_at=utcnow(),
        )
        db.session.add(row)
        db.session.commit()
        emit_leaderboard_refresh(current_user.id)
        save_target = (request.form.get("save_target") or "journal").strip().lower()
        if save_target not in ("journal", "journal_feed"):
            save_target = "journal"
        if save_target == "journal_feed":
            flash("Outdoor session saved to your training journal and shared on the feed.", "success")
            return redirect(url_for("social.feed"))
        flash("Outdoor session saved to your training journal.", "success")
        return redirect(url_for("social.profile") + "#gym-journal")

    return render_template("outdoor_log.html", kinds=OUTDOOR_KINDS)


@bp.route("/exercise/<kind>")
@login_required
def exercise_history(kind: str):
    if kind not in OUTDOOR_KINDS:
        abort(404)
    rows = (
        OutdoorActivity.query.filter_by(user_id=current_user.id, kind=kind)
        .order_by(OutdoorActivity.posted_at.asc())
        .all()
    )
    chart_labels: list[str] = []
    chart_scores: list[float] = []
    chart_best: list[float] = []
    best = 0.0
    for r in rows:
        chart_labels.append(r.posted_at.date().isoformat())
        chart_scores.append(round(float(r.score), 2))
        best = max(best, float(r.score))
        chart_best.append(round(best, 2))
    return render_template(
        "outdoor_exercise.html",
        kind=kind,
        rows=list(reversed(rows)),
        chart_labels=chart_labels,
        chart_scores=chart_scores,
        chart_best=chart_best,
    )
