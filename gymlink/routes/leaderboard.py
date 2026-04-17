from __future__ import annotations

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from extensions import db
from models import Match, PersonalRecord, Streak, User

bp = Blueprint("leaderboard", __name__)


def _friend_users(user_id: int):
    matches = Match.query.filter(
        (Match.user_a_id == user_id) | (Match.user_b_id == user_id)
    ).all()
    friend_ids = []
    for m in matches:
        friend_ids.append(m.user_b_id if m.user_a_id == user_id else m.user_a_id)
    if not friend_ids:
        return []
    return User.query.filter(User.id.in_(friend_ids)).order_by(User.name).all()


def _streak_rows_for_users(user_ids: list[int]):
    if not user_ids:
        return {}
    rows = Streak.query.filter(Streak.user_id.in_(user_ids)).all()
    return {r.user_id: r for r in rows}


def _pr_for_exercise(user_ids: list[int], exercise: str):
    if not user_ids:
        return {}
    rows = PersonalRecord.query.filter(
        PersonalRecord.user_id.in_(user_ids),
        PersonalRecord.exercise_name == exercise,
    ).all()
    return {r.user_id: r for r in rows}


DEFAULT_PR_EXERCISE = "Bench Press"
PR_EXERCISES = [
    "Bench Press",
    "Squat",
    "Deadlift",
    "Overhead Press",
    "Pull Ups",
]


@bp.route("/leaderboard")
@login_required
def home():
    friends = _friend_users(current_user.id)
    friend_ids = [f.id for f in friends]
    streak_map = _streak_rows_for_users(friend_ids + [current_user.id])

    exercise = (request.args.get("exercise") or DEFAULT_PR_EXERCISE).strip()
    if exercise not in PR_EXERCISES:
        exercise = DEFAULT_PR_EXERCISE

    pr_map = _pr_for_exercise(friend_ids + [current_user.id], exercise)

    streak_ranked = sorted(
        friends,
        key=lambda u: (streak_map.get(u.id).current_streak if streak_map.get(u.id) else 0),
        reverse=True,
    )

    def pr_weight(uid):
        pr = pr_map.get(uid)
        return pr.best_weight_lbs if pr else 0.0

    pr_ranked = sorted(friends, key=lambda u: pr_weight(u.id), reverse=True)

    me_streak = streak_map.get(current_user.id)
    return render_template(
        "leaderboard.html",
        friends=friends,
        streak_ranked=streak_ranked,
        pr_ranked=pr_ranked,
        streak_map=streak_map,
        pr_map=pr_map,
        me_streak=me_streak,
        exercise=exercise,
        pr_exercises=PR_EXERCISES,
    )
