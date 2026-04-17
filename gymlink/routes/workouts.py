from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import PersonalRecord, Streak, Workout
from models import utcnow
from realtime import emit_leaderboard_refresh

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
        exercise_name = (request.form.get("exercise_name") or "").strip()
        weight_raw = request.form.get("weight_lbs")
        reps_raw = request.form.get("reps")

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

        workout = Workout(
            user_id=current_user.id,
            exercise_name=exercise_name,
            weight_lbs=weight_lbs,
            reps=reps,
            logged_at=utcnow(),
        )
        db.session.add(workout)
        db.session.flush()

        is_pr = _apply_pr(current_user.id, exercise_name, weight_lbs, reps)
        _update_streak_for_log(current_user.id)
        db.session.commit()

        emit_leaderboard_refresh(current_user.id)

        if is_pr:
            return redirect(url_for("workouts.log_workout", new_pr=exercise_name))
        flash("Workout logged.", "success")
        return redirect(url_for("workouts.log_workout"))

    return render_template("log_workout.html")
