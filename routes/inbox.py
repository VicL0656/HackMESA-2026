from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import FriendGroup, FriendGroupMember, Match, Notification, User
from models import utcnow
from notification_helpers import ensure_streak_risk_notification

bp = Blueprint("inbox", __name__, url_prefix="/inbox")


def _priority_kinds() -> tuple[str, ...]:
    return ("friend_request", "friend_pr", "streak_risk")


def _inbox_dm_rows(user_id: int) -> list[tuple[Match, User]]:
    matches = (
        Match.query.filter((Match.user_a_id == user_id) | (Match.user_b_id == user_id))
        .order_by(Match.matched_at.desc())
        .all()
    )
    out: list[tuple[Match, User]] = []
    for m in matches:
        oid = m.user_b_id if m.user_a_id == user_id else m.user_a_id
        u = db.session.get(User, oid)
        if u:
            out.append((m, u))
    return out


def _inbox_group_previews(user_id: int) -> list[tuple[FriendGroup, list[User]]]:
    member_rows = FriendGroupMember.query.filter_by(user_id=user_id).all()
    gids = [r.group_id for r in member_rows]
    groups: list[FriendGroup] = []
    if gids:
        groups = (
            FriendGroup.query.filter(FriendGroup.id.in_(gids))
            .order_by(FriendGroup.updated_at.desc())
            .all()
        )
    previews: list[tuple[FriendGroup, list[User]]] = []
    for g in groups:
        mids = FriendGroupMember.query.filter_by(group_id=g.id).all()
        uids = [x.user_id for x in mids]
        members = User.query.filter(User.id.in_(uids)).all() if uids else []
        by_id = {u.id: u for u in members}
        previews.append((g, [by_id[i] for i in uids if i in by_id]))
    return previews


@bp.route("")
@login_required
def inbox_home():
    ensure_streak_risk_notification(current_user.id)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    kinds = _priority_kinds()
    unread = (
        Notification.query.filter_by(user_id=current_user.id, read_at=None)
        .order_by(Notification.priority.desc(), Notification.created_at.desc())
        .limit(200)
        .all()
    )
    priority = [n for n in unread if n.kind in kinds]
    other = [n for n in unread if n.kind not in kinds]

    read_recent = (
        Notification.query.filter(
            Notification.user_id == current_user.id,
            Notification.read_at.isnot(None),
        )
        .order_by(Notification.read_at.desc())
        .limit(40)
        .all()
    )

    dm_rows = _inbox_dm_rows(current_user.id)
    group_previews = _inbox_group_previews(current_user.id)

    return render_template(
        "inbox.html",
        priority_rows=priority,
        other_unread=other,
        read_recent=read_recent,
        dm_rows=dm_rows,
        group_previews=group_previews,
    )


@bp.post("/read/<int:notif_id>")
@login_required
def mark_read(notif_id: int):
    n = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first()
    if n and n.read_at is None:
        n.read_at = utcnow()
        db.session.commit()
    return redirect(request.referrer or url_for("inbox.inbox_home"))


@bp.post("/read-all")
@login_required
def mark_all_read():
    now = utcnow()
    for n in Notification.query.filter_by(user_id=current_user.id, read_at=None).all():
        n.read_at = now
    db.session.commit()
    flash("Inbox cleared.", "success")
    return redirect(url_for("inbox.inbox_home"))
