from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import PersonalRecord, Streak, Workout
from models import utcnow
from realtime import emit_leaderboard_refresh
from uploads_util import file_was_chosen, save_uploaded_image
from split_presets import today_plan
from workout_helpers import recalculate_prs_for_user, recompute_streak_for_user


def _norm_ex_name(s: str) -> str:
    return (s or "").strip()


def is_run_like(name: str) -> bool:
    n = _norm_ex_name(name).lower()
    if not n:
        return False
    return any(
        k in n
        for k in ("mile", "run", "jog", "5k", "10k", "cardio", "treadmill", "interval", "track", "sprint")
    )


def _plan_reps_default(ex: dict) -> int:
    r = ex.get("reps")
    if r is None or (isinstance(r, str) and not str(r).strip()):
        return 1
    try:
        return max(1, int(r))
    except (TypeError, ValueError):
        return 1


def _plan_sets_int_or_none(ex: dict) -> int | None:
    s = ex.get("sets")
    if s is None or (isinstance(s, str) and not str(s).strip()):
        return None
    try:
        v = int(s)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _plan_seconds_int_or_none(ex: dict) -> int | None:
    s = ex.get("seconds")
    if s is None or (isinstance(s, str) and not str(s).strip()):
        return None
    try:
        v = int(s)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_float_loose(raw) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _parse_int_opt(raw) -> int | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        v = int(s)
        return v if v > 0 else None
    except ValueError:
        return None


def _build_log_lines_from_form(
    *,
    follow_split: bool,
    off_plan: bool,
    manual_other: bool,
    plan_exercises: list[dict],
) -> tuple[list[dict[str, object]] | None, str | None]:
    """Returns (lines, error_message)."""
    names = request.form.getlist("entry_name")
    weights = request.form.getlist("entry_weight")
    reps_in = request.form.getlist("entry_reps")
    sets_in = request.form.getlist("entry_sets")
    dur_in = request.form.getlist("entry_duration")
    notes_in = request.form.getlist("entry_note")
    n = len(names)
    if not (
        n == len(weights) == len(reps_in) == len(sets_in) == len(dur_in) == len(notes_in)
    ):
        return None, "Invalid form data — refresh and try again."

    if follow_split and n != len(plan_exercises):
        return None, f"This day’s plan has {len(plan_exercises)} exercises — keep all rows."

    lines: list[dict[str, object]] = []
    for i in range(n):
        raw_name = names[i]
        name = _norm_ex_name(raw_name)
        raw_plan = plan_exercises[i] if follow_split and i < len(plan_exercises) else None
        if isinstance(raw_plan, str):
            ex_plan: dict = {"name": raw_plan, "sets": None, "reps": None, "seconds": None, "note": ""}
        elif isinstance(raw_plan, dict):
            ex_plan = raw_plan
        else:
            ex_plan = {}

        if follow_split:
            if not name:
                return None, "Every exercise from today’s plan must stay filled in."
            expected = _norm_ex_name(str(ex_plan.get("name") or ""))
            if name.casefold() != expected.casefold():
                return None, "Exercise names must match today’s plan, or check “Something other than today’s split”."

        if not follow_split:
            if not name:
                continue

        weight_lbs = _parse_float_loose(weights[i])
        if follow_split:
            note = _norm_ex_name(str(ex_plan.get("note") or "")) or None
        else:
            note = _norm_ex_name(notes_in[i]) or None

        if follow_split and not manual_other:
            reps = _plan_reps_default(ex_plan)
            num_sets = _plan_sets_int_or_none(ex_plan)
            ps = _plan_seconds_int_or_none(ex_plan)
            if is_run_like(name):
                duration_seconds = _parse_int_opt(dur_in[i])
            elif ps is not None:
                duration_seconds = ps
            else:
                duration_seconds = None
        elif follow_split and manual_other:
            r = _parse_int_opt(reps_in[i])
            reps = max(1, r if r is not None else 1)
            num_sets = _parse_int_opt(sets_in[i])
            duration_seconds = _parse_int_opt(dur_in[i])
        else:
            r = _parse_int_opt(reps_in[i])
            reps = max(1, r if r is not None else 1)
            num_sets = _parse_int_opt(sets_in[i])
            duration_seconds = _parse_int_opt(dur_in[i])

        lines.append(
            {
                "exercise_name": name,
                "weight_lbs": weight_lbs,
                "reps": int(reps),
                "num_sets": num_sets,
                "duration_seconds": duration_seconds,
                "exercise_note": note,
            }
        )

    if not lines:
        return None, "Add at least one exercise with a name."

    if not manual_other:
        for ln in lines:
            if float(ln["weight_lbs"]) < 0 or int(ln["reps"]) < 1:
                return None, "Each lift needs a non-negative weight and at least 1 rep (or use Manual / other)."
    else:
        for ln in lines:
            if float(ln["weight_lbs"]) < 0:
                ln["weight_lbs"] = 0.0
            if int(ln["reps"]) < 1:
                ln["reps"] = 1

    return lines, None

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


def _coerce_plan_row(x: object) -> dict:
    if isinstance(x, str):
        return {"name": x, "sets": None, "reps": None, "seconds": None, "note": ""}
    if isinstance(x, dict):
        return x
    return {"name": "", "sets": None, "reps": None, "seconds": None, "note": ""}


def _log_page_ctx():
    wd = date.today().weekday()
    sp = today_plan(current_user.workout_split, wd)
    plan_exercises: list[dict] = []
    if sp and not sp.get("rest"):
        plan_exercises = [_coerce_plan_row(x) for x in (sp.get("exercises") or [])]
    return {
        "split_plan": sp,
        "split_weekday": wd,
        "plan_exercises": plan_exercises,
        "run_like": is_run_like,
    }


def _serialize_line_items(lines_out: list[dict[str, object]]) -> list[dict]:
    out: list[dict] = []
    for ln in lines_out:
        out.append(
            {
                "exercise_name": str(ln["exercise_name"]),
                "weight_lbs": float(ln["weight_lbs"]),
                "reps": int(ln["reps"]),
                "num_sets": ln.get("num_sets"),
                "duration_seconds": ln.get("duration_seconds"),
                "exercise_note": ln.get("exercise_note"),
            }
        )
    return out


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
            flash("Rest day saved to your training journal.", "success")
            return redirect(url_for("social.profile") + "#gym-journal")

        caption = (request.form.get("caption") or "").strip() or None
        manual_other = request.form.get("manual_other") == "1"
        off_plan = request.form.get("off_plan") == "1"
        raw_sd = request.form.get("split_weekday", type=int)
        split_weekday = raw_sd if raw_sd is not None and 0 <= raw_sd <= 6 else date.today().weekday()

        plan_data = today_plan(current_user.workout_split, split_weekday)
        plan_exercises: list[dict] = []
        if plan_data and not plan_data.get("rest"):
            plan_exercises = list(plan_data.get("exercises") or [])

        follow_split = (not off_plan) and len(plan_exercises) > 0

        lines_out, err = _build_log_lines_from_form(
            follow_split=follow_split,
            off_plan=off_plan,
            manual_other=manual_other,
            plan_exercises=plan_exercises,
        )
        if err:
            flash(err, "error")
            return render_template("log_workout.html", **_log_page_ctx())

        fphoto = request.files.get("photo")
        photo = save_uploaded_image(fphoto, f"w_{current_user.id}")
        if file_was_chosen(fphoto) and not photo:
            flash(
                "Photo was not saved. Use JPG, PNG, WEBP, or GIF under the 25 MB limit (HEIC/iPhone often needs “Most Compatible” in Camera settings).",
                "warning",
            )

        first = lines_out[0]
        serialized = _serialize_line_items(lines_out)
        line_items = serialized if len(serialized) > 1 else None

        workout = Workout(
            user_id=current_user.id,
            exercise_name=str(first["exercise_name"]),
            weight_lbs=float(first["weight_lbs"]),
            reps=int(first["reps"]),
            logged_at=utcnow(),
            caption=caption,
            photo_path=photo,
            is_pr_session=False,
            is_rest_day=False,
            num_sets=first["num_sets"] if first.get("num_sets") else None,
            duration_seconds=first["duration_seconds"] if first.get("duration_seconds") else None,
            exercise_note=first.get("exercise_note") if first.get("exercise_note") else None,
            split_weekday=split_weekday,
            off_plan=off_plan,
            line_items=line_items,
        )
        db.session.add(workout)
        db.session.flush()

        any_pr = False
        pr_exercise_name = ""
        pr_weight = 0.0
        pr_reps = 1
        if not manual_other:
            for ln in lines_out:
                en = str(ln["exercise_name"])
                wl = float(ln["weight_lbs"])
                rp = int(ln["reps"])
                if wl > 0 and _apply_pr(current_user.id, en, wl, rp):
                    any_pr = True
                    if not pr_exercise_name:
                        pr_exercise_name = en
                        pr_weight = wl
                        pr_reps = rp

        workout.is_pr_session = bool(any_pr)
        _update_streak_for_log(current_user.id)
        db.session.commit()

        emit_leaderboard_refresh(current_user.id)

        if any_pr and pr_exercise_name:
            from notification_helpers import notify_friends_of_pr

            notify_friends_of_pr(current_user, workout, pr_exercise_name, pr_weight, pr_reps)
            db.session.commit()
            return redirect(url_for("social.profile", new_pr=pr_exercise_name) + "#gym-journal")
        flash("Saved to your training journal.", "success")
        return redirect(url_for("social.profile") + "#gym-journal")

    return render_template("log_workout.html", **_log_page_ctx())


@bp.route("/<int:workout_id>/edit", methods=["GET", "POST"])
@login_required
def edit_workout(workout_id: int):
    w = Workout.query.filter_by(id=workout_id, user_id=current_user.id).first()
    if not w or w.is_rest_day:
        abort(404)
    if w.line_items and isinstance(w.line_items, list) and len(w.line_items) > 1:
        flash("Multi-exercise posts can’t be edited yet. Delete this post and log again if you need to change lifts.", "info")
        return redirect(url_for("social.profile") + "#gym-journal")
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
        return redirect(url_for("social.profile") + "#gym-journal")
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
    return redirect(url_for("social.profile") + "#gym-journal")
