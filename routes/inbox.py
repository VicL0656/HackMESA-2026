from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Notification
from models import utcnow
from notification_helpers import ensure_streak_risk_notification

bp = Blueprint("inbox", __name__, url_prefix="/inbox")


def _priority_kinds() -> tuple[str, ...]:
    return ("friend_request", "friend_pr", "streak_risk")


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

    return render_template(
        "inbox.html",
        priority_rows=priority,
        other_unread=other,
        read_recent=read_recent,
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
