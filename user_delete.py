"""Hard-delete a user and dependent rows (no soft-delete)."""

from __future__ import annotations

from sqlalchemy import or_

from extensions import db
from models import (
    CheckIn,
    DailyChallengeComplete,
    FriendFavorite,
    FriendGroup,
    FriendGroupMember,
    FriendRequest,
    Goal,
    GroupMessage,
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
    FriendFavorite.query.filter(
        or_(FriendFavorite.user_id == uid, FriendFavorite.friend_user_id == uid),
    ).delete(synchronize_session=False)
    DailyChallengeComplete.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Swipe.query.filter(
        or_(Swipe.swiper_id == uid, Swipe.swipee_id == uid),
    ).delete(synchronize_session=False)

    for g in FriendGroup.query.filter_by(creator_id=uid).all():
        gid = g.id
        FriendGroupMember.query.filter_by(group_id=gid).delete(synchronize_session=False)
        GroupMessage.query.filter_by(group_id=gid).delete(synchronize_session=False)
        db.session.delete(g)
    member_gids = [r.group_id for r in FriendGroupMember.query.filter_by(user_id=uid).all()]
    FriendGroupMember.query.filter_by(user_id=uid).delete(synchronize_session=False)
    GroupMessage.query.filter_by(sender_id=uid).delete(synchronize_session=False)
    for gid in set(member_gids):
        if FriendGroupMember.query.filter_by(group_id=gid).count() == 0:
            GroupMessage.query.filter_by(group_id=gid).delete(synchronize_session=False)
            fg = db.session.get(FriendGroup, gid)
            if fg:
                db.session.delete(fg)

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
