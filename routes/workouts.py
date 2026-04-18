from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import PersonalRecord, Streak, Workout
from models import utcnow
from realtime import emit_leaderboard_refresh
from uploads_util import file_was_chosen, save_uploaded_image
from workout_helpers import recalculate_prs_for_user, recompute_streak_for_user

bp = Blueprint("workouts", __name__, url_prefix="/workouts")


def _update_streak_for_log(user_id: int) -> None:
    streak = Streak.query.filter_by(user_id=user_id).first()
    if not streak:
        streak = Streak(user_id=user_id, current_streak=0, longest_streak=0, last_logged_date=None)
        db.session.add(streak)
        db.session.flush()

    today = date.today()
    last = streak.last_logged_date

    if last == today:
        return

    if last is None:
        streak.current_streak = 1
    elif last == today - timedelta(days=1):
        streak.current_streak += 1
    else:
        streak.current_streak = 1

    streak.last_logged_date = today
    streak.longest_streak = max(streak.longest_streak or 0, streak.current_streak)


def _apply_pr(user_id: int, exercise_name: str, weight_lbs: float, reps: int) -> bool:
    pr = PersonalRecord.query.filter_by(user_id=user_id, exercise_name=exercise_name).first()
    now = utcnow()
    if not pr:
        db.session.add(
            PersonalRecord(
                user_id=user_id,
                exercise_name=exercise_name,
                best_weight_lbs=weight_lbs,
                best_reps=reps,
                achieved_at=now,
            )
        )
        return True

    improved = weight_lbs > pr.best_weight_lbs or (
        weight_lbs == pr.best_weight_lbs and reps > pr.best_reps
    )
    if improved:
        pr.best_weight_lbs = weight_lbs
        pr.best_reps = reps
        pr.achieved_at = now
        return True
    return False


@bp.route("/log", methods=["GET", "POST"])
@login_required
def log_workout():
    if request.method == "POST":
        if request.form.get("rest_day") == "1":
            w = Workout(
                user_id=current_user.id,
                exercise_name="Rest day",
                weight_lbs=0,
                reps=1,
                logged_at=utcnow(),
                caption=None,
                photo_path=None,
                is_pr_session=False,
                is_rest_day=True,
            )
            db.session.add(w)
            _update_streak_for_log(current_user.id)
            db.session.commit()
            emit_leaderboard_refresh(current_user.id)
            flash("Rest day logged — streak preserved.", "success")
            return redirect(url_for("social.feed"))

        exercise_name = (request.form.get("exercise_name") or "").strip()
        weight_raw = request.form.get("weight_lbs")
        reps_raw = request.form.get("reps")
        caption = (request.form.get("caption") or "").strip() or None

        if not exercise_name:
            flash("Exercise name is required.", "error")
            return render_template("log_workout.html")

        try:
            weight_lbs = float(weight_raw)
            reps = int(reps_raw)
        except (TypeError, ValueError):
            flash("Weight and reps must be valid numbers.", "error")
            return render_template("log_workout.html")

        if weight_lbs < 0 or reps < 1:
            flash("Enter a non-negative weight and at least 1 rep.", "error")
            return render_template("log_workout.html")

        fphoto = request.files.get("photo")
        photo = save_uploaded_image(fphoto, f"w_{current_user.id}")
        if file_was_chosen(fphoto) and not photo:
            flash(
                "Photo was not saved. Use JPG, PNG, WEBP, or GIF under the 25 MB limit (HEIC/iPhone often needs “Most Compatible” in Camera settings).",
                "warning",
            )

        workout = Workout(
            user_id=current_user.id,
            exercise_name=exercise_name,
            weight_lbs=weight_lbs,
            reps=reps,
            logged_at=utcnow(),
            caption=caption,
            photo_path=photo,
            is_pr_session=False,
            is_rest_day=False,
        )
        db.session.add(workout)
        db.session.flush()

        is_pr = _apply_pr(current_user.id, exercise_name, weight_lbs, reps)
        workout.is_pr_session = bool(is_pr)
        _update_streak_for_log(current_user.id)
        db.session.commit()

        emit_leaderboard_refresh(current_user.id)

        if is_pr:
            from notification_helpers import notify_friends_of_pr

            notify_friends_of_pr(current_user, workout, exercise_name, weight_lbs, reps)
            db.session.commit()
            return redirect(url_for("workouts.log_workout", new_pr=exercise_name))
        flash("Workout posted.", "success")
        return redirect(url_for("social.feed"))

    return render_template("log_workout.html")


@bp.route("/<int:workout_id>/edit", methods=["GET", "POST"])
@login_required
def edit_workout(workout_id: int):
    w = Workout.query.filter_by(id=workout_id, user_id=current_user.id).first()
    if not w or w.is_rest_day:
        abort(404)
    if request.method == "POST":
        exercise_name = (request.form.get("exercise_name") or "").strip()
        try:
            weight_lbs = float(request.form.get("weight_lbs") or "")
            reps = int(request.form.get("reps") or "")
        except (TypeError, ValueError):
            flash("Invalid numbers.", "error")
            return render_template("edit_workout.html", workout=w)
        if not exercise_name or weight_lbs < 0 or reps < 1:
            flash("Check exercise, weight, and reps.", "error")
            return render_template("edit_workout.html", workout=w)
        w.exercise_name = exercise_name
        w.weight_lbs = weight_lbs
        w.reps = reps
        w.caption = (request.form.get("caption") or "").strip() or None
        fphoto = request.files.get("photo")
        photo = save_uploaded_image(fphoto, f"w_{current_user.id}")
        if file_was_chosen(fphoto) and not photo:
            flash(
                "Photo was not saved. Use JPG, PNG, WEBP, or GIF under the 25 MB limit.",
                "warning",
            )
        if photo:
            w.photo_path = photo
        db.session.flush()
        recalculate_prs_for_user(current_user.id)
        recompute_streak_for_user(current_user.id)
        db.session.commit()
        emit_leaderboard_refresh(current_user.id)
        flash("Workout updated.", "success")
        return redirect(url_for("social.feed"))
    return render_template("edit_workout.html", workout=w)


@bp.post("/<int:workout_id>/delete")
@login_required
def delete_workout(workout_id: int):
    w = Workout.query.filter_by(id=workout_id, user_id=current_user.id).first()
    if not w:
        abort(404)
    db.session.delete(w)
    db.session.flush()
    recalculate_prs_for_user(current_user.id)
    recompute_streak_for_user(current_user.id)
    db.session.commit()
    emit_leaderboard_refresh(current_user.id)
    flash("Workout deleted.", "info")
    return redirect(url_for("social.feed"))
