from __future__ import annotations

from urllib.parse import quote

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, desc, or_

from extensions import db
from models import (
    FriendFavorite,
    FriendGroup,
    FriendGroupMember,
    FriendRequest,
    Goal,
    GroupChallengeComplete,
    GroupMessage,
    Match,
    Message,
    OutdoorActivity,
    Streak,
    Swipe,
    User,
    WeightLog,
    Workout,
)
from models import utcnow
from uploads_util import save_uploaded_image
from username_utils import (
    assign_username_if_missing,
    normalize_username,
    resolve_user_by_email_or_username,
)

bp = Blueprint("social", __name__)

MAX_GC_MEMBERS = 16


def _redirect_after_friend_form(default_endpoint: str = "social.add_friend"):
    """Optional same-origin path from POST `redirect_to` (e.g. return to Home)."""
    n = (request.form.get("redirect_to") or "").strip()
    if (
        n.startswith("/")
        and not n.startswith("//")
        and "\n" not in n
        and "\r" not in n
        and len(n) < 512
    ):
        return redirect(n)
    return redirect(url_for(default_endpoint))


def _friend_ids(user_id: int) -> set[int]:
    matches = Match.query.filter(
        (Match.user_a_id == user_id) | (Match.user_b_id == user_id)
    ).all()
    out = set()
    for m in matches:
        out.add(m.user_b_id if m.user_a_id == user_id else m.user_a_id)
    return out


def _school_domain(user: User) -> str | None:
    em = (getattr(user, "school_email", None) or "").strip().lower()
    if not em or "@" not in em:
        return None
    return em.split("@", 1)[1]


def _suggested_friends_same_gym(user_id: int, home_gym_id: int | None, limit: int = 8) -> list[User]:
    if not home_gym_id:
        return []
    matched = _friend_ids(user_id)
    q = User.query.filter(User.home_gym_id == home_gym_id, User.id != user_id)
    if matched:
        q = q.filter(User.id.not_in(matched))
    rows = (
        q.outerjoin(Streak, Streak.user_id == User.id)
        .order_by(desc(Streak.current_streak), User.name)
        .limit(limit)
        .all()
    )
    return list(rows)


def _remove_friendship_pair(a_id: int, b_id: int) -> None:
    low, high = _ordered_pair(a_id, b_id)
    m = Match.query.filter_by(user_a_id=low, user_b_id=high).first()
    if m:
        Message.query.filter_by(match_id=m.id).delete()
        db.session.delete(m)
    Swipe.query.filter(
        or_(
            and_(Swipe.swiper_id == a_id, Swipe.swipee_id == b_id),
            and_(Swipe.swiper_id == b_id, Swipe.swipee_id == a_id),
        )
    ).delete(synchronize_session=False)
    FriendRequest.query.filter(
        or_(
            and_(FriendRequest.from_user_id == a_id, FriendRequest.to_user_id == b_id),
            and_(FriendRequest.from_user_id == b_id, FriendRequest.to_user_id == a_id),
        )
    ).delete(synchronize_session=False)


def _ordered_pair(a_id: int, b_id: int) -> tuple[int, int]:
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


def _ensure_match(user_a_id: int, user_b_id: int) -> Match:
    low, high = _ordered_pair(user_a_id, user_b_id)
    existing = Match.query.filter_by(user_a_id=low, user_b_id=high).first()
    if existing:
        return existing
    m = Match(user_a_id=low, user_b_id=high, matched_at=utcnow())
    db.session.add(m)
    return m


def _finalize_friend_requests(a_id: int, b_id: int) -> None:
    for row in FriendRequest.query.filter(
        or_(
            and_(FriendRequest.from_user_id == a_id, FriendRequest.to_user_id == b_id),
            and_(FriendRequest.from_user_id == b_id, FriendRequest.to_user_id == a_id),
        )
    ).all():
        row.status = "accepted"


@bp.post("/friends/add")
@login_required
def friends_add():
    raw = (request.form.get("friend_handle") or request.form.get("email") or "").strip()
    if not raw:
        flash("Enter your friend’s @username or the sign-in they use for GymLink.", "error")
        return _redirect_after_friend_form()

    other = resolve_user_by_email_or_username(raw)
    if not other:
        flash("No GymLink account matches that handle or sign-in.", "error")
        return _redirect_after_friend_form()

    if other.id == current_user.id:
        flash("You cannot add yourself.", "error")
        return _redirect_after_friend_form()

    low, high = _ordered_pair(current_user.id, other.id)
    if Match.query.filter_by(user_a_id=low, user_b_id=high).first():
        flash("You are already gym friends with that lifter.", "info")
        return _redirect_after_friend_form()

    reverse = FriendRequest.query.filter_by(
        from_user_id=other.id,
        to_user_id=current_user.id,
        status="pending",
    ).first()
    if reverse:
        _ensure_match(current_user.id, other.id)
        _finalize_friend_requests(current_user.id, other.id)
        from notification_helpers import mark_friend_requests_between_users_read

        mark_friend_requests_between_users_read(current_user.id, other.id)
        db.session.commit()
        flash(f"You and {other.name} are now gym friends.", "success")
        return _redirect_after_friend_form()

    outgoing = FriendRequest.query.filter_by(
        from_user_id=current_user.id,
        to_user_id=other.id,
    ).first()
    if outgoing:
        if outgoing.status == "pending":
            flash("Friend request already sent.", "info")
            return _redirect_after_friend_form()
        if outgoing.status == "declined":
            outgoing.status = "pending"
            outgoing.created_at = utcnow()
            db.session.commit()
            flash("Friend request sent again.", "success")
            return _redirect_after_friend_form()
        flash("You are already connected with that lifter.", "info")
        return _redirect_after_friend_form()

    fr = FriendRequest(
        from_user_id=current_user.id,
        to_user_id=other.id,
        status="pending",
        created_at=utcnow(),
    )
    db.session.add(fr)
    db.session.flush()
    from notification_helpers import notify_friend_request_created

    notify_friend_request_created(fr)
    db.session.commit()
    flash(f"Friend request sent to {other.name}.", "success")
    return _redirect_after_friend_form()


@bp.post("/friends/favorite/<int:other_id>")
@login_required
def friends_toggle_favorite(other_id: int):
    if other_id == current_user.id:
        flash("Invalid.", "error")
        return redirect(request.referrer or url_for("leaderboard.home"))
    low, high = _ordered_pair(current_user.id, other_id)
    if not Match.query.filter_by(user_a_id=low, user_b_id=high).first():
        flash("You can only favorite gym friends.", "error")
        return redirect(request.referrer or url_for("leaderboard.home"))
    row = FriendFavorite.query.filter_by(
        user_id=current_user.id,
        friend_user_id=other_id,
    ).first()
    if row:
        db.session.delete(row)
        flash("Removed from best friends.", "info")
    else:
        db.session.add(FriendFavorite(user_id=current_user.id, friend_user_id=other_id))
        flash("Pinned to best friends.", "success")
    db.session.commit()
    return redirect(request.referrer or url_for("leaderboard.home"))


@bp.post("/friends/remove/<int:other_id>")
@login_required
def friends_remove(other_id: int):
    if other_id == current_user.id:
        flash("Invalid.", "error")
        return redirect(url_for("social.profile"))
    low, high = _ordered_pair(current_user.id, other_id)
    if not Match.query.filter_by(user_a_id=low, user_b_id=high).first():
        flash("You are not gym friends with that user.", "info")
        return redirect(request.referrer or url_for("social.profile"))
    _remove_friendship_pair(current_user.id, other_id)
    db.session.commit()
    flash("Removed from gym friends.", "success")
    return redirect(request.referrer or url_for("social.profile"))


@bp.post("/friends/requests/<int:request_id>/accept")
@login_required
def friend_request_accept(request_id: int):
    req = db.session.get(FriendRequest, request_id)
    if not req or req.to_user_id != current_user.id or req.status != "pending":
        flash("That request is not available.", "error")
        return redirect(url_for("social.profile"))

    _ensure_match(req.from_user_id, req.to_user_id)
    _finalize_friend_requests(req.from_user_id, req.to_user_id)
    from notification_helpers import mark_friend_request_notifications_read

    mark_friend_request_notifications_read(current_user.id, req.id)
    db.session.commit()
    flash("Friend request accepted.", "success")
    return redirect(url_for("social.profile"))


@bp.post("/friends/requests/<int:request_id>/decline")
@login_required
def friend_request_decline(request_id: int):
    req = db.session.get(FriendRequest, request_id)
    if not req or req.to_user_id != current_user.id or req.status != "pending":
        flash("That request is not available.", "error")
        return redirect(url_for("social.profile"))

    from notification_helpers import mark_friend_request_notifications_read

    mark_friend_request_notifications_read(current_user.id, req.id)
    req.status = "declined"
    db.session.commit()
    flash("Friend request declined.", "info")
    return redirect(url_for("social.profile"))


def _feed_timestamp(item_type: str, obj: Workout | OutdoorActivity):
    if item_type == "workout":
        return obj.logged_at
    return obj.posted_at


@bp.route("/feed")
@login_required
def feed():
    friend_ids = list(_friend_ids(current_user.id))
    visible_ids = list({*friend_ids, current_user.id})
    workouts: list[Workout] = []
    outdoors: list[OutdoorActivity] = []
    if visible_ids:
        workouts = (
            Workout.query.filter(Workout.user_id.in_(visible_ids))
            .order_by(Workout.logged_at.desc())
            .limit(40)
            .all()
        )
        outdoors = (
            OutdoorActivity.query.filter(OutdoorActivity.user_id.in_(visible_ids))
            .order_by(OutdoorActivity.posted_at.desc())
            .limit(40)
            .all()
        )
    feed_items: list[tuple[str, Workout | OutdoorActivity]] = []
    for w in workouts:
        feed_items.append(("workout", w))
    for a in outdoors:
        feed_items.append(("outdoor", a))
    feed_items.sort(key=lambda t: _feed_timestamp(t[0], t[1]), reverse=True)
    feed_items = feed_items[:40]

    users_by_id = {
        u.id: u for u in User.query.filter(User.id.in_(visible_ids)).all()
    } if visible_ids else {}
    suggested = _suggested_friends_same_gym(
        current_user.id, getattr(current_user, "home_gym_id", None)
    )
    return render_template(
        "feed.html",
        feed_items=feed_items,
        users_by_id=users_by_id,
        suggested_friends=suggested,
    )


def _mark_match_read(m: Match, uid: int) -> None:
    t = utcnow()
    if m.user_a_id == uid:
        m.user_a_last_read_at = t
    else:
        m.user_b_last_read_at = t


@bp.get("/matches/<int:match_id>/poll")
@login_required
def match_messages_poll(match_id: int):
    m = db.session.get(Match, match_id)
    if not m or current_user.id not in (m.user_a_id, m.user_b_id):
        abort(404)
    after = request.args.get("after", type=int) or 0
    rows = (
        Message.query.filter(Message.match_id == m.id, Message.id > after)
        .order_by(Message.id.asc())
        .limit(50)
        .all()
    )
    return jsonify(
        {
            "ok": True,
            "messages": [
                {
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "content": msg.content,
                    "sent_at": msg.sent_at.isoformat(),
                }
                for msg in rows
            ],
        }
    )


@bp.route("/matches/<int:match_id>", methods=["GET", "POST"])
@login_required
def match_thread(match_id: int):
    from realtime import emit_dm_message

    m = db.session.get(Match, match_id)
    if not m or current_user.id not in (m.user_a_id, m.user_b_id):
        abort(404)

    other_id = m.user_b_id if m.user_a_id == current_user.id else m.user_a_id
    other = db.session.get(User, other_id)

    if request.method == "POST":
        content = (request.form.get("content") or "").strip()
        if not content:
            if request.form.get("xhr") == "1":
                return jsonify({"ok": False, "error": "empty"}), 400
            flash("Message cannot be empty.", "error")
            return redirect(url_for("social.match_thread", match_id=match_id))
        msg = Message(match_id=m.id, sender_id=current_user.id, content=content, sent_at=utcnow())
        db.session.add(msg)
        db.session.flush()
        db.session.commit()
        payload = {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "content": msg.content,
            "sent_at": msg.sent_at.isoformat(),
        }
        emit_dm_message(m.id, payload)
        if request.form.get("xhr") == "1":
            return jsonify({"ok": True, "message": payload})
        return redirect(url_for("social.match_thread", match_id=match_id))

    threshold = m.user_a_last_read_at if m.user_a_id == current_user.id else m.user_b_last_read_at
    messages = Message.query.filter_by(match_id=m.id).order_by(Message.sent_at.asc()).all()
    highlight_ids = {
        msg.id
        for msg in messages
        if msg.sender_id != current_user.id and (threshold is None or msg.sent_at > threshold)
    }
    _mark_match_read(m, current_user.id)
    db.session.commit()

    return render_template(
        "match_thread.html",
        match=m,
        other=other,
        messages=messages,
        message_highlight_ids=highlight_ids,
    )


def _gym_friend_users(user_id: int) -> list[User]:
    matches = Match.query.filter(
        (Match.user_a_id == user_id) | (Match.user_b_id == user_id)
    ).all()
    out: list[User] = []
    for m in matches:
        oid = m.user_b_id if m.user_a_id == user_id else m.user_a_id
        u = db.session.get(User, oid)
        if u:
            out.append(u)
    out.sort(key=lambda u: u.name.lower())
    return out


@bp.route("/groups")
@login_required
def groups_home():
    member_rows = FriendGroupMember.query.filter_by(user_id=current_user.id).all()
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
    return render_template("groups.html", group_previews=previews)


@bp.route("/groups/new", methods=["GET", "POST"])
@login_required
def groups_new():
    friends = _gym_friend_users(current_user.id)
    ctx = {"friends": friends, "max_gc_members": MAX_GC_MEMBERS}
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:120] or "Group chat"
        raw = request.form.getlist("member_id")
        pick: list[int] = []
        for x in raw:
            try:
                pick.append(int(x))
            except (TypeError, ValueError):
                pass
        friend_set = _friend_ids(current_user.id)
        pick = [i for i in pick if i in friend_set and i != current_user.id]
        pick = list(dict.fromkeys(pick))
        if not pick:
            flash("Choose at least one gym friend for the group.", "error")
            return render_template("group_new.html", **ctx)
        if len(pick) + 1 > MAX_GC_MEMBERS:
            flash(f"Groups can have at most {MAX_GC_MEMBERS} people including you.", "error")
            return render_template("group_new.html", **ctx)
        now = utcnow()
        g = FriendGroup(name=name, creator_id=current_user.id, created_at=now, updated_at=now)
        db.session.add(g)
        db.session.flush()
        for uid in (current_user.id, *pick):
            db.session.add(FriendGroupMember(group_id=g.id, user_id=uid, joined_at=now))
        db.session.commit()
        flash("Group chat created.", "success")
        return redirect(url_for("social.group_thread", group_id=g.id))
    return render_template("group_new.html", **ctx)


@bp.get("/groups/<int:group_id>/poll")
@login_required
def group_messages_poll(group_id: int):
    g = db.session.get(FriendGroup, group_id)
    if not g:
        abort(404)
    if not FriendGroupMember.query.filter_by(group_id=g.id, user_id=current_user.id).first():
        abort(404)
    after = request.args.get("after", type=int) or 0
    rows = (
        GroupMessage.query.filter(GroupMessage.group_id == g.id, GroupMessage.id > after)
        .order_by(GroupMessage.id.asc())
        .limit(50)
        .all()
    )
    uids = {m.sender_id for m in rows}
    by_id = {u.id: u for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}
    return jsonify(
        {
            "ok": True,
            "messages": [
                {
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "sender_username": (by_id.get(msg.sender_id).username if by_id.get(msg.sender_id) else ""),
                    "content": msg.content,
                    "sent_at": msg.sent_at.isoformat(),
                }
                for msg in rows
            ],
        }
    )


@bp.route("/groups/<int:group_id>", methods=["GET", "POST"])
@login_required
def group_thread(group_id: int):
    from datetime import date as date_cls

    from realtime import emit_group_message

    g = db.session.get(FriendGroup, group_id)
    if not g:
        abort(404)
    if not FriendGroupMember.query.filter_by(group_id=g.id, user_id=current_user.id).first():
        abort(404)

    if request.method == "POST":
        part = (request.form.get("form_part") or "message").strip()
        if part == "rename":
            name = (request.form.get("name") or "").strip()[:120]
            if name:
                g.name = name
                g.updated_at = utcnow()
                db.session.commit()
                flash("Group name updated.", "success")
            return redirect(url_for("social.group_thread", group_id=group_id))
        if part == "add_members":
            raw = request.form.getlist("member_id")
            pick: list[int] = []
            for x in raw:
                try:
                    pick.append(int(x))
                except (TypeError, ValueError):
                    pass
            friend_set = _friend_ids(current_user.id)
            mids = FriendGroupMember.query.filter_by(group_id=g.id).all()
            cur_ids = {r.user_id for r in mids}
            n = len(cur_ids)
            for uid in pick:
                if uid in cur_ids or uid not in friend_set or uid == current_user.id:
                    continue
                if n >= MAX_GC_MEMBERS:
                    flash(f"Groups can have at most {MAX_GC_MEMBERS} people.", "error")
                    break
                db.session.add(FriendGroupMember(group_id=g.id, user_id=uid, joined_at=utcnow()))
                cur_ids.add(uid)
                n += 1
            g.updated_at = utcnow()
            db.session.commit()
            flash("Members updated.", "success")
            return redirect(url_for("social.group_thread", group_id=group_id))
        if part == "challenge":
            title = (request.form.get("challenge_title") or "").strip()[:200]
            raw_d = (request.form.get("challenge_day") or "").strip()
            d: date_cls | None = None
            if raw_d:
                try:
                    d = date_cls.fromisoformat(raw_d)
                except ValueError:
                    d = None
            g.challenge_title = title or None
            g.challenge_day = d
            g.updated_at = utcnow()
            db.session.commit()
            flash("Group challenge saved.", "success")
            return redirect(url_for("social.group_thread", group_id=group_id))
        if part == "challenge_done":
            today = utcnow().date()
            if g.challenge_day and g.challenge_title:
                exists = GroupChallengeComplete.query.filter_by(
                    group_id=g.id,
                    user_id=current_user.id,
                    challenge_day=g.challenge_day,
                ).first()
                if not exists:
                    db.session.add(
                        GroupChallengeComplete(
                            group_id=g.id,
                            user_id=current_user.id,
                            challenge_day=g.challenge_day,
                        )
                    )
                    g.updated_at = utcnow()
                    db.session.commit()
            return redirect(url_for("social.group_thread", group_id=group_id))

        content = (request.form.get("content") or "").strip()
        if not content:
            if request.form.get("xhr") == "1":
                return jsonify({"ok": False, "error": "empty"}), 400
            flash("Message cannot be empty.", "error")
            return redirect(url_for("social.group_thread", group_id=group_id))
        gm = GroupMessage(group_id=g.id, sender_id=current_user.id, content=content, sent_at=utcnow())
        db.session.add(gm)
        g.updated_at = utcnow()
        db.session.flush()
        db.session.commit()
        payload = {
            "id": gm.id,
            "sender_id": gm.sender_id,
            "content": gm.content,
            "sent_at": gm.sent_at.isoformat(),
        }
        emit_group_message(g.id, payload)
        if request.form.get("xhr") == "1":
            return jsonify({"ok": True, "message": payload})
        return redirect(url_for("social.group_thread", group_id=group_id))

    rows = FriendGroupMember.query.filter_by(group_id=g.id).all()
    uids = [r.user_id for r in rows]
    members = User.query.filter(User.id.in_(uids)).all() if uids else []
    by_id = {u.id: u for u in members}
    ordered_members = [by_id[i] for i in uids if i in by_id]
    messages = (
        GroupMessage.query.filter_by(group_id=g.id).order_by(GroupMessage.sent_at.asc()).all()
    )
    challenge_done_ids: set[int] = set()
    if g.challenge_day:
        challenge_done_ids = {
            r.user_id
            for r in GroupChallengeComplete.query.filter_by(
                group_id=g.id,
                challenge_day=g.challenge_day,
            ).all()
        }
    friends = _gym_friend_users(current_user.id)
    addable = [u for u in friends if u.id not in uids]
    return render_template(
        "group_thread.html",
        group=g,
        members=ordered_members,
        members_by_id=by_id,
        messages=messages,
        challenge_done_ids=challenge_done_ids,
        addable_friends=addable,
    )


@bp.post("/groups/<int:group_id>/leave")
@login_required
def group_leave(group_id: int):
    g = db.session.get(FriendGroup, group_id)
    if not g:
        abort(404)
    row = FriendGroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    if not row:
        abort(404)
    was_creator = g.creator_id == current_user.id
    db.session.delete(row)
    db.session.flush()
    remaining = FriendGroupMember.query.filter_by(group_id=group_id).count()
    if remaining == 0:
        GroupChallengeComplete.query.filter_by(group_id=group_id).delete(synchronize_session=False)
        GroupMessage.query.filter_by(group_id=group_id).delete(synchronize_session=False)
        db.session.delete(g)
    elif was_creator:
        nxt = (
            FriendGroupMember.query.filter_by(group_id=group_id)
            .order_by(FriendGroupMember.joined_at.asc())
            .first()
        )
        if nxt:
            g.creator_id = nxt.user_id
    db.session.commit()
    flash("You left the group.", "info")
    return redirect(url_for("social.groups_home"))


@bp.route("/add-friend")
@login_required
def add_friend():
    connect_username = assign_username_if_missing(current_user)
    friend_connect_url = url_for(
        "social.connect_friend", username=connect_username, _external=True
    )
    qr_data = quote(friend_connect_url, safe="")
    return render_template(
        "add_friend.html",
        friend_connect_url=friend_connect_url,
        qr_data=qr_data,
    )


@bp.route("/connect/<username>")
def connect_friend(username: str):
    un = normalize_username(username)
    if not un:
        abort(404)
    target = User.query.filter_by(username=un).first()
    if not target:
        abort(404)
    return render_template("connect.html", target=target)


@bp.post("/profile/update")
@login_required
def profile_update():
    import json

    from split_presets import (
        PRESET_KEYS,
        build_preset,
        coerce_day_focus_list,
        load_v2_split,
    )
    from workout_split_util import serialize_from_request

    current_user.school = (request.form.get("school") or "").strip() or None
    preset = (request.form.get("split_preset") or "keep").strip().lower()
    posted_focus = [request.form.get(f"day_focus_{i}", "").strip().lower() for i in range(7)]

    if preset in PRESET_KEYS:
        built = build_preset(preset)
        if built:
            full = json.loads(built)
            full["day_focus"] = coerce_day_focus_list(preset, full.get("days") or [], posted_focus)
            current_user.workout_split = json.dumps(full, separators=(",", ":"))
    elif preset == "keep":
        data = load_v2_split(current_user.workout_split)
        if data:
            p = str(data.get("preset") or "ppl").lower()
            days = data.get("days") or []
            data["day_focus"] = coerce_day_focus_list(p, days, posted_focus)
            current_user.workout_split = json.dumps(data, separators=(",", ":"))
    elif preset == "legacy":
        current_user.workout_split = serialize_from_request(request.form)
    db.session.commit()
    flash("School and split saved.", "success")
    return redirect(url_for("social.profile"))


@bp.post("/profile/body-weight")
@login_required
def profile_body_weight():
    raw = (request.form.get("weight_lbs") or "").strip()
    if not raw:
        flash("Enter your current weight.", "error")
        return redirect(url_for("social.profile"))
    try:
        w = float(raw)
    except ValueError:
        flash("Weight must be a number.", "error")
        return redirect(url_for("social.profile"))
    if w <= 30 or w > 800:
        flash("Enter a realistic body weight (lb).", "error")
        return redirect(url_for("social.profile"))
    current_user.current_body_weight_lbs = w
    db.session.add(WeightLog(user_id=current_user.id, weight_lbs=w, visibility="private"))
    db.session.commit()
    flash("Body weight saved.", "success")
    return redirect(url_for("social.profile"))


@bp.post("/profile/photo")
@login_required
def profile_photo():
    max_pfp = int(
        current_app.config.get("MAX_PROFILE_PHOTO_BYTES", 25 * 1024 * 1024)
    )
    path = save_uploaded_image(
        request.files.get("photo"),
        f"avatar_{current_user.id}",
        max_bytes=max_pfp,
    )
    if path:
        current_user.photo_url = path
        db.session.commit()
        flash("Profile photo updated.", "success")
    else:
        max_mb = max(1, round(max_pfp / (1024 * 1024)))
        flash(
            f"Could not save image. Use JPG, PNG, or WEBP under {max_mb}MB.",
            "error",
        )
    return redirect(url_for("social.profile"))


@bp.post("/profile/goals/add")
@login_required
def goal_add():
    title = (request.form.get("title") or "").strip()
    unit = (request.form.get("unit") or "").strip() or "lbs"
    try:
        target = float(request.form.get("target_value") or "")
        current_v = float(request.form.get("current_value") or 0)
    except (TypeError, ValueError):
        flash("Goal needs numeric target.", "error")
        return redirect(url_for("social.profile"))
    if not title or target <= 0:
        flash("Title and positive target are required.", "error")
        return redirect(url_for("social.profile"))
    dl = None
    raw_d = (request.form.get("deadline") or "").strip()
    if raw_d:
        from datetime import datetime as dtmod

        try:
            dl = dtmod.strptime(raw_d, "%Y-%m-%d").date()
        except ValueError:
            pass
    db.session.add(
        Goal(
            user_id=current_user.id,
            title=title[:200],
            target_value=target,
            current_value=current_v,
            unit=unit[:40],
            deadline=dl,
            completed=False,
        )
    )
    db.session.commit()
    flash("Goal added.", "success")
    return redirect(url_for("social.profile"))


@bp.post("/profile/goals/<int:goal_id>/toggle")
@login_required
def goal_toggle(goal_id: int):
    g = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if g:
        g.completed = not g.completed
        db.session.commit()
    return redirect(url_for("social.profile"))


@bp.post("/profile/goals/<int:goal_id>/delete")
@login_required
def goal_delete(goal_id: int):
    g = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if g:
        db.session.delete(g)
        db.session.commit()
        flash("Goal removed.", "info")
    return redirect(url_for("social.profile"))


@bp.post("/profile/goals/<int:goal_id>/update")
@login_required
def goal_update(goal_id: int):
    g = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if not g:
        return redirect(url_for("social.profile"))
    try:
        g.current_value = float(request.form.get("current_value") or 0)
    except (TypeError, ValueError):
        flash("Current value must be a number.", "error")
        return redirect(url_for("social.profile"))
    db.session.commit()
    flash("Goal progress updated.", "success")
    return redirect(url_for("social.profile"))


@bp.route("/profile")
@login_required
def profile():
    from models import PersonalRecord, Streak

    streak = Streak.query.filter_by(user_id=current_user.id).first()
    prs = (
        PersonalRecord.query.filter_by(user_id=current_user.id)
        .order_by(PersonalRecord.exercise_name.asc())
        .all()
    )
    matches = Match.query.filter(
        (Match.user_a_id == current_user.id) | (Match.user_b_id == current_user.id)
    ).order_by(Match.matched_at.desc()).all()
    match_rows = []
    for m in matches:
        oid = m.user_b_id if m.user_a_id == current_user.id else m.user_a_id
        match_rows.append((m, db.session.get(User, oid)))

    incoming = (
        FriendRequest.query.filter_by(to_user_id=current_user.id, status="pending")
        .order_by(FriendRequest.created_at.desc())
        .all()
    )
    incoming_rows = []
    for fr in incoming:
        incoming_rows.append((fr, db.session.get(User, fr.from_user_id)))

    outgoing = (
        FriendRequest.query.filter_by(from_user_id=current_user.id, status="pending")
        .order_by(FriendRequest.created_at.desc())
        .all()
    )
    outgoing_rows = []
    for fr in outgoing:
        outgoing_rows.append((fr, db.session.get(User, fr.to_user_id)))

    latest_w = (
        WeightLog.query.filter_by(user_id=current_user.id)
        .order_by(WeightLog.logged_at.desc())
        .first()
    )
    suggested = _suggested_friends_same_gym(
        current_user.id, getattr(current_user, "home_gym_id", None)
    )
    recent_workouts = (
        Workout.query.filter_by(user_id=current_user.id)
        .order_by(Workout.logged_at.desc())
        .limit(20)
        .all()
    )

    import copy

    from split_presets import (
        ensure_day_focus,
        focus_options_for_preset,
        load_v2_split,
        parse_v2,
        preset_display_name,
        summary_lines_v2,
    )
    from workout_split_util import card_lines, form_context

    _fc = form_context(current_user.workout_split)
    _lines, _legacy = card_lines(current_user.workout_split)
    _pv = parse_v2(current_user.workout_split)
    split_is_v2 = _pv is not None
    split_v2_lines = summary_lines_v2(current_user.workout_split) if split_is_v2 else []
    split_preset_key = str(_pv.get("preset") or "") if _pv else ""
    split_preset_label = preset_display_name(split_preset_key) if split_is_v2 else ""
    split_focus_options: list[tuple[str, str]] = []
    split_day_focus: list[str] | None = None
    if split_is_v2 and split_preset_key:
        fd = load_v2_split(current_user.workout_split)
        if fd:
            fd2 = copy.deepcopy(fd)
            split_day_focus = list(ensure_day_focus(fd2))
            split_focus_options = focus_options_for_preset(split_preset_key)

    wl_rows = (
        WeightLog.query.filter_by(user_id=current_user.id)
        .order_by(WeightLog.logged_at.desc())
        .limit(60)
        .all()
    )
    weight_chart_points = [{"t": r.logged_at.isoformat(), "w": r.weight_lbs} for r in reversed(wl_rows)]
    prog_ex = (request.args.get("prog_ex") or "Bench Press").strip()[:120] or "Bench Press"
    prog_rows = (
        Workout.query.filter_by(user_id=current_user.id, exercise_name=prog_ex, is_rest_day=False)
        .order_by(Workout.logged_at.asc())
        .limit(120)
        .all()
    )
    prog_points = [{"t": w.logged_at.isoformat(), "w": w.weight_lbs} for w in prog_rows]

    return render_template(
        "profile.html",
        streak=streak,
        prs=prs,
        match_rows=match_rows,
        incoming_rows=incoming_rows,
        outgoing_rows=outgoing_rows,
        latest_weight=latest_w,
        suggested_friends=suggested,
        recent_workouts=recent_workouts,
        split_days=_fc["days"],
        split_display_lines=_lines,
        split_display_legacy=_legacy,
        split_is_v2=split_is_v2,
        split_v2_lines=split_v2_lines,
        split_preset_key=split_preset_key,
        split_preset_label=split_preset_label,
        split_focus_options=split_focus_options,
        split_day_focus=split_day_focus,
        weight_chart_points=weight_chart_points,
        prog_exercise=prog_ex,
        prog_points=prog_points,
    )
