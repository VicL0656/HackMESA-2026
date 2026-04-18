"""Hard-delete a user and dependent rows (no soft-delete)."""

from __future__ import annotations

from sqlalchemy import or_

from extensions import db
from models import (
    CheckIn,
    FriendRequest,
    Goal,
    Match,
    Message,
    Notification,
    OutdoorActivity,
    PasswordResetToken,
    PersonalRecord,
    Streak,
    Swipe,
    User,
    WeightLog,
    Workout,
)


def delete_user_account(user_id: int) -> None:
    uid = user_id

    match_ids = [
        m.id
        for m in Match.query.filter(
            or_(Match.user_a_id == uid, Match.user_b_id == uid),
        ).all()
    ]
    for mid in match_ids:
        Message.query.filter_by(match_id=mid).delete(synchronize_session=False)
    Match.query.filter(or_(Match.user_a_id == uid, Match.user_b_id == uid)).delete(
        synchronize_session=False
    )

    Notification.query.filter_by(user_id=uid).delete(synchronize_session=False)
    PasswordResetToken.query.filter_by(user_id=uid).delete(synchronize_session=False)

    FriendRequest.query.filter(
        or_(FriendRequest.from_user_id == uid, FriendRequest.to_user_id == uid),
    ).delete(synchronize_session=False)
    Swipe.query.filter(
        or_(Swipe.swiper_id == uid, Swipe.swipee_id == uid),
    ).delete(synchronize_session=False)

    Goal.query.filter_by(user_id=uid).delete(synchronize_session=False)
    WeightLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Workout.query.filter_by(user_id=uid).delete(synchronize_session=False)
    PersonalRecord.query.filter_by(user_id=uid).delete(synchronize_session=False)
    OutdoorActivity.query.filter_by(user_id=uid).delete(synchronize_session=False)
    CheckIn.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Streak.query.filter_by(user_id=uid).delete(synchronize_session=False)

    u = db.session.get(User, uid)
    if u:
        db.session.delete(u)
