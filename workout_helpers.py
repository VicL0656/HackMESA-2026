"""PR and streak recalculation from workout history (used after edit/delete/rest log)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_

from extensions import db
from models import PersonalRecord, Streak, Workout
from models import utcnow


def _day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def workout_activity_dates(user_id: int) -> list[date]:
    """Calendar days with any workout or rest log."""
    rows = Workout.query.filter_by(user_id=user_id).all()
    out: set[date] = set()
    for w in rows:
        if w.logged_at:
            out.add(w.logged_at.date())
    return sorted(out)


def recompute_streak_for_user(user_id: int) -> None:
    """Rebuild streak row from all workout/rest days for this user."""
    streak = Streak.query.filter_by(user_id=user_id).first()
    if not streak:
        streak = Streak(user_id=user_id, current_streak=0, longest_streak=0, last_logged_date=None)
        db.session.add(streak)
        db.session.flush()

    days = workout_activity_dates(user_id)
    if not days:
        streak.current_streak = 0
        streak.longest_streak = max(0, streak.longest_streak or 0)
        streak.last_logged_date = None
        return

    longest = 0
    run = 0
    prev: date | None = None
    for d in days:
        if prev is None:
            run = 1
        elif d == prev + timedelta(days=1):
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev = d

    last = days[-1]
    tail = 1
    for i in range(len(days) - 2, -1, -1):
        if days[i + 1] - days[i] == timedelta(days=1):
            tail += 1
        else:
            break

    streak.current_streak = tail
    streak.longest_streak = max(longest, streak.longest_streak or 0)
    streak.last_logged_date = last


def recalculate_prs_for_user(user_id: int) -> None:
    """Delete and rebuild PersonalRecord rows from non-rest workouts."""
    PersonalRecord.query.filter_by(user_id=user_id).delete()
    workouts = (
        Workout.query.filter_by(user_id=user_id)
        .filter(or_(Workout.is_rest_day.is_(False), Workout.is_rest_day.is_(None)))
        .order_by(Workout.logged_at.asc(), Workout.id.asc())
        .all()
    )
    by_ex: dict[str, list[Workout]] = defaultdict(list)
    for w in workouts:
        by_ex[w.exercise_name].append(w)

    now = utcnow()
    for ex, rows in by_ex.items():
        best = rows[0]
        for w in rows[1:]:
            if w.weight_lbs > best.weight_lbs or (
                w.weight_lbs == best.weight_lbs and w.reps > best.reps
            ):
                best = w
        db.session.add(
            PersonalRecord(
                user_id=user_id,
                exercise_name=ex,
                best_weight_lbs=best.weight_lbs,
                best_reps=best.reps,
                achieved_at=best.logged_at or now,
            )
        )


def user_has_workout_on_date(user_id: int, day: date) -> bool:
    start, end = _day_bounds_utc(day)
    return (
        Workout.query.filter(
            Workout.user_id == user_id,
            Workout.logged_at >= start,
            Workout.logged_at < end,
        ).first()
        is not None
    )
