"""Create inbox notifications for friend requests, PRs, streak reminders."""

from __future__ import annotations

from datetime import date, timedelta

from flask import url_for

from sqlalchemy import and_, or_

from extensions import db
from models import FriendRequest, Match, Notification, Streak, User, Workout
from models import utcnow


def _friend_user_ids(user_id: int) -> list[int]:
    rows = Match.query.filter((Match.user_a_id == user_id) | (Match.user_b_id == user_id)).all()
    out: list[int] = []
    for m in rows:
        out.append(m.user_b_id if m.user_a_id == user_id else m.user_a_id)
    return out


def notify_friend_request_created(fr: FriendRequest) -> None:
    """Recipient sees a priority inbox item."""
    if not fr or fr.status != "pending":
        return
    sender = db.session.get(User, fr.from_user_id)
    name = sender.name if sender else "Someone"
    dedupe = f"friend_request:{fr.id}"
    exists = Notification.query.filter_by(user_id=fr.to_user_id, dedupe_key=dedupe).first()
    if exists:
        return
    action = url_for("social.profile") + "#incoming-requests"
    n = Notification(
        user_id=fr.to_user_id,
        kind="friend_request",
        title=f"Friend request from {name}",
        body=f"@{sender.username if sender else 'user'} wants to connect on GymLink.",
        action_url=action,
        priority=True,
        dedupe_key=dedupe,
        friend_request_id=fr.id,
    )
    db.session.add(n)


def mark_friend_request_notifications_read(user_id: int, fr_id: int) -> None:
    now = utcnow()
    for n in Notification.query.filter_by(user_id=user_id, friend_request_id=fr_id).all():
        if n.read_at is None:
            n.read_at = now


def mark_friend_requests_between_users_read(a_id: int, b_id: int) -> None:
    """Dismiss inbox friend-request rows after the pair becomes gym friends (either direction)."""
    rows = FriendRequest.query.filter(
        or_(
            and_(FriendRequest.from_user_id == a_id, FriendRequest.to_user_id == b_id),
            and_(FriendRequest.from_user_id == b_id, FriendRequest.to_user_id == a_id),
        )
    ).all()
    for fr in rows:
        mark_friend_request_notifications_read(fr.to_user_id, fr.id)


def notify_friends_of_pr(actor: User, workout: Workout, exercise_name: str, weight_lbs: float, reps: int) -> None:
    """Gym friends get a priority line when you log a session that sets a PR."""
    body = f"{exercise_name}: {weight_lbs:g} lb × {reps}"
    for fid in _friend_user_ids(actor.id):
        dedupe = f"friend_pr:{workout.id}:{fid}"
        if Notification.query.filter_by(user_id=fid, dedupe_key=dedupe).first():
            continue
        n = Notification(
            user_id=fid,
            kind="friend_pr",
            title=f"{actor.name} hit a PR",
            body=body,
            action_url=url_for("social.feed"),
            priority=True,
            dedupe_key=dedupe,
        )
        db.session.add(n)


def ensure_streak_risk_notification(user_id: int) -> None:
    """
    If the user still has a streak but has not logged today, remind once per calendar day.
    (Last log was yesterday — log today before midnight local calendar handling uses server date.)
    """
    today = date.today()
    streak = Streak.query.filter_by(user_id=user_id).first()
    if not streak or not streak.current_streak or streak.current_streak <= 0:
        return
    last = streak.last_logged_date
    if last is None or last >= today:
        return
    if last < today - timedelta(days=1):
        return
    dedupe = f"streak_risk:{today.isoformat()}"
    if Notification.query.filter_by(user_id=user_id, dedupe_key=dedupe).first():
        return
    n = Notification(
        user_id=user_id,
        kind="streak_risk",
        title="Streak at risk today",
        body=f"You are on a {streak.current_streak}-day streak. Log a workout or a rest day before the day ends to keep it.",
        action_url=url_for("workouts.log_workout"),
        priority=True,
        dedupe_key=dedupe,
    )
    db.session.add(n)


