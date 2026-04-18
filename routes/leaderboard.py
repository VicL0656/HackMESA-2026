from __future__ import annotations

from datetime import date

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (
    DailyChallenge,
    DailyChallengeComplete,
    FriendFavorite,
    Gym,
    Match,
    PersonalRecord,
    Streak,
    User,
    utcnow,
)
from routes.social import _friend_ids, _suggested_friends_same_gym
from tom_friend import repair_tom_friendship_if_missing
from workout_helpers import user_has_workout_on_date

bp = Blueprint("leaderboard", __name__)

DEFAULT_PR_EXERCISE = "Bench Press"
PR_EXERCISES = [
    "Bench Press",
    "Squat",
    "Deadlift",
    "Overhead Press",
    "Pull Ups",
]


def _friend_users(user_id: int) -> list[User]:
    matches = Match.query.filter(
        (Match.user_a_id == user_id) | (Match.user_b_id == user_id)
    ).all()
    friend_ids: list[int] = []
    for m in matches:
        friend_ids.append(m.user_b_id if m.user_a_id == user_id else m.user_a_id)
    if not friend_ids:
        return []
    return User.query.filter(User.id.in_(friend_ids)).order_by(User.name).all()


def _friend_match_map(user_id: int) -> dict[int, int]:
    out: dict[int, int] = {}
    for m in Match.query.filter(
        (Match.user_a_id == user_id) | (Match.user_b_id == user_id)
    ).all():
        oid = m.user_b_id if m.user_a_id == user_id else m.user_a_id
        out[oid] = m.id
    return out


def _streak_rows_for_users(user_ids: list[int]) -> dict[int, Streak]:
    if not user_ids:
        return {}
    rows = Streak.query.filter(Streak.user_id.in_(user_ids)).all()
    return {r.user_id: r for r in rows}


def _pr_for_exercise(user_ids: list[int], exercise: str) -> dict[int, PersonalRecord]:
    if not user_ids:
        return {}
    rows = PersonalRecord.query.filter(
        PersonalRecord.user_id.in_(user_ids),
        PersonalRecord.exercise_name == exercise,
    ).all()
    return {r.user_id: r for r in rows}


def _favorite_friend_ids(user_id: int) -> set[int]:
    rows = FriendFavorite.query.filter_by(user_id=user_id).all()
    return {r.friend_user_id for r in rows}


def _ensure_daily_challenge(day: date) -> DailyChallenge:
    row = DailyChallenge.query.filter_by(challenge_date=day).first()
    if row:
        return row
    templates = [
        ("Log any workout or rest day", "Count for today when you log training or a rest day (UTC day)."),
        ("Move with intent", "Any logged session today keeps your chain honest."),
        ("Show up", "One session today — however you train."),
        ("Consistency wins", "Log something today so friends can see you showed up."),
    ]
    idx = day.toordinal() % len(templates)
    title, body = templates[idx]
    row = DailyChallenge(challenge_date=day, title=title, body=body)
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        again = DailyChallenge.query.filter_by(challenge_date=day).first()
        if again:
            return again
        raise
    return row


def _sync_challenge_for_users(day: date, user_ids: list[int]) -> None:
    if not user_ids:
        return
    changed = False
    for uid in user_ids:
        if not user_has_workout_on_date(uid, day):
            continue
        exists = DailyChallengeComplete.query.filter_by(user_id=uid, challenge_date=day).first()
        if exists:
            continue
        db.session.add(DailyChallengeComplete(user_id=uid, challenge_date=day))
        changed = True
    if changed:
        db.session.commit()


def _challenge_completion_map(day: date, user_ids: list[int]) -> set[int]:
    if not user_ids:
        return set()
    rows = DailyChallengeComplete.query.filter(
        DailyChallengeComplete.challenge_date == day,
        DailyChallengeComplete.user_id.in_(user_ids),
    ).all()
    return {r.user_id for r in rows}


def _sort_friends(
    users: list[User],
    *,
    sort: str,
    streak_map: dict[int, Streak],
    pr_map: dict[int, PersonalRecord],
) -> list[User]:
    sort = (sort or "streak").strip().lower()
    if sort == "pr":

        def pr_key(u: User) -> float:
            pr = pr_map.get(u.id)
            return pr.best_weight_lbs if pr else 0.0

        return sorted(users, key=pr_key, reverse=True)

    def streak_key(u: User) -> int:
        s = streak_map.get(u.id)
        return s.current_streak if s else 0

    return sorted(users, key=streak_key, reverse=True)


def _build_suggestions(me: User, my_friends: set[int]) -> list[dict]:
    """Non-friends with reasons: mutual connections, same gym, same school."""
    mutual: dict[int, int] = {}
    for fid in my_friends:
        for oid in _friend_ids(fid):
            if oid == me.id or oid in my_friends:
                continue
            mutual[oid] = mutual.get(oid, 0) + 1

    tags_by: dict[int, list[str]] = {}
    for oid, n in mutual.items():
        label = "1 mutual friend" if n == 1 else f"{n} mutual friends"
        tags_by.setdefault(oid, []).append(label)

    for u in _suggested_friends_same_gym(me.id, me.home_gym_id, limit=12):
        if u.id == me.id or u.id in my_friends:
            continue
        tags_by.setdefault(u.id, []).append("Same gym")

    school = (me.school or "").strip()
    if school:
        q = User.query.filter(User.school == school, User.id != me.id)
        if my_friends:
            q = q.filter(User.id.notin_(my_friends))
        for u in q.order_by(User.name).limit(12).all():
            tags_by.setdefault(u.id, []).append("Same college")

    uids = list(tags_by.keys())
    if not uids:
        return []
    users = User.query.filter(User.id.in_(uids)).all()
    by_uid = {u.id: u for u in users}

    def score(uid: int) -> int:
        u = by_uid.get(uid)
        if not u:
            return 0
        s = mutual.get(uid, 0) * 100
        if me.home_gym_id and u.home_gym_id == me.home_gym_id:
            s += 20
        if school and (u.school or "").strip() == school:
            s += 10
        return s

    ordered = sorted(tags_by.keys(), key=lambda i: (-score(i), i))
    return [{"user": by_uid[i], "tags": tags_by[i]} for i in ordered if i in by_uid]


@bp.route("/leaderboard")
@login_required
def home():
    repair_tom_friendship_if_missing(current_user.id)
    friends = _friend_users(current_user.id)
    friend_match_map = _friend_match_map(current_user.id)
    friend_ids = [f.id for f in friends]
    my_friend_set = set(friend_ids)
    streak_map = _streak_rows_for_users(friend_ids + [current_user.id])

    exercise = (request.args.get("exercise") or DEFAULT_PR_EXERCISE).strip()
    if exercise not in PR_EXERCISES:
        exercise = DEFAULT_PR_EXERCISE

    pr_map = _pr_for_exercise(friend_ids + [current_user.id], exercise)

    tab = (request.args.get("tab") or "friends").strip().lower()
    if tab not in ("friends", "challenge", "suggested"):
        tab = "friends"

    sort = (request.args.get("sort") or "streak").strip().lower()
    if sort not in ("streak", "pr"):
        sort = "streak"

    favorite_ids = _favorite_friend_ids(current_user.id)
    fav_users = [u for u in friends if u.id in favorite_ids]
    other_users = [u for u in friends if u.id not in favorite_ids]
    fav_sorted = _sort_friends(fav_users, sort=sort, streak_map=streak_map, pr_map=pr_map)
    other_sorted = _sort_friends(
        other_users + [current_user],
        sort=sort,
        streak_map=streak_map,
        pr_map=pr_map,
    )

    ranked_all = _sort_friends(
        list(friends) + [current_user],
        sort=sort,
        streak_map=streak_map,
        pr_map=pr_map,
    )
    medal_emojis = ("🥇", "🥈", "🥉")
    medal_by_id: dict[int, str] = {}
    for idx, u in enumerate(ranked_all[:3]):
        medal_by_id[u.id] = medal_emojis[idx]

    today = utcnow().date()
    challenge = _ensure_daily_challenge(today)
    _sync_challenge_for_users(today, [current_user.id, *friend_ids])
    completed_ids = _challenge_completion_map(today, [current_user.id, *friend_ids])
    challenge_friends_done = [u for u in friends if u.id in completed_ids]
    challenge_friends_done.sort(key=lambda u: u.name.lower())
    me_done = current_user.id in completed_ids

    suggestions = _build_suggestions(current_user, my_friend_set)

    me_streak = streak_map.get(current_user.id)
    me_pr = pr_map.get(current_user.id)

    gym_by_id: dict[int, Gym] = {}
    gids = {u.home_gym_id for u in friends if u.home_gym_id}
    if gids:
        for g in Gym.query.filter(Gym.id.in_(gids)).all():
            gym_by_id[g.id] = g

    return render_template(
        "leaderboard.html",
        friends=friends,
        friend_match_map=friend_match_map,
        fav_sorted=fav_sorted,
        other_sorted=other_sorted,
        favorite_ids=favorite_ids,
        streak_map=streak_map,
        pr_map=pr_map,
        me_streak=me_streak,
        me_pr=me_pr,
        exercise=exercise,
        pr_exercises=PR_EXERCISES,
        active_tab=tab,
        friend_sort=sort,
        challenge=challenge,
        challenge_today=today,
        me_challenge_done=me_done,
        challenge_completed_ids=completed_ids,
        challenge_friends_done=challenge_friends_done,
        suggestions=suggestions,
        gym_by_id=gym_by_id,
        medal_by_id=medal_by_id,
    )
