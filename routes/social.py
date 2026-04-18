from __future__ import annotations

from urllib.parse import quote

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, desc, or_

from extensions import db
from models import FriendRequest, Goal, Match, Message, OutdoorActivity, Streak, Swipe, User, WeightLog, Workout
from models import utcnow
from uploads_util import save_uploaded_image
from username_utils import (
    assign_username_if_missing,
    normalize_username,
    resolve_user_by_email_or_username,
)

bp = Blueprint("social", __name__)


def _friend_ids(user_id: int) -> set[int]:
    matches = Match.query.filter(
        (Match.user_a_id == user_id) | (Match.user_b_id == user_id)
    ).all()
    out = set()
    for m in matches:
        out.add(m.user_b_id if m.user_a_id == user_id else m.user_a_id)
    return out


def _matched_user_ids(user_id: int) -> set[int]:
    return _friend_ids(user_id)


def _swiped_user_ids(user_id: int) -> set[int]:
    rows = Swipe.query.filter_by(swiper_id=user_id).all()
    return {r.swipee_id for r in rows}


def _school_domain(user: User) -> str | None:
    em = (getattr(user, "school_email", None) or "").strip().lower()
    if not em or "@" not in em:
        return None
    return em.split("@", 1)[1]


def _next_swipe_candidate(
    user_id: int,
    same_school_only: bool = False,
    school: str | None = None,
    me: User | None = None,
):
    matched = _matched_user_ids(user_id)
    swiped = _swiped_user_ids(user_id)
    me = me or db.session.get(User, user_id)
    q = User.query.filter(User.id != user_id)
    if same_school_only and school:
        q = q.filter(User.school == school)
    candidates = [u for u in q.all() if u.id not in matched and u.id not in swiped]
    if not candidates:
        return None
    my_dom = _school_domain(me) if me else None

    def streak_val(u: User) -> int:
        s = Streak.query.filter_by(user_id=u.id).first()
        return s.current_streak if s else 0

    def tier(u: User) -> int:
        if my_dom and _school_domain(u) == my_dom:
            return 0
        if me and me.home_gym_id and u.home_gym_id == me.home_gym_id:
            return 1
        return 2

    candidates.sort(key=lambda u: (tier(u), -streak_val(u), u.name.lower()))
    return candidates[0]


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


def _try_create_match(a_id: int, b_id: int) -> Match | None:
    if a_id == b_id:
        return None
    low, high = (a_id, b_id) if a_id < b_id else (b_id, a_id)
    existing = Match.query.filter_by(user_a_id=low, user_b_id=high).first()
    if existing:
        return existing
    mutual = (
        Swipe.query.filter_by(swiper_id=a_id, swipee_id=b_id, direction="right").first()
        and Swipe.query.filter_by(swiper_id=b_id, swipee_id=a_id, direction="right").first()
    )
    if not mutual:
        return None
    m = Match(user_a_id=low, user_b_id=high, matched_at=utcnow())
    db.session.add(m)
    return m


@bp.post("/friends/add")
@login_required
def friends_add():
    raw = (request.form.get("friend_handle") or request.form.get("email") or "").strip()
    if not raw:
        flash("Enter your friend’s @username or the sign-in they use for GymLink.", "error")
        return redirect(url_for("social.profile"))

    other = resolve_user_by_email_or_username(raw)
    if not other:
        flash("No GymLink account matches that handle or sign-in.", "error")
        return redirect(url_for("social.profile"))

    if other.id == current_user.id:
        flash("You cannot add yourself.", "error")
        return redirect(url_for("social.profile"))

    low, high = _ordered_pair(current_user.id, other.id)
    if Match.query.filter_by(user_a_id=low, user_b_id=high).first():
        flash("You are already gym friends with that lifter.", "info")
        return redirect(url_for("social.profile"))

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
        return redirect(url_for("social.profile"))

    outgoing = FriendRequest.query.filter_by(
        from_user_id=current_user.id,
        to_user_id=other.id,
    ).first()
    if outgoing:
        if outgoing.status == "pending":
            flash("Friend request already sent.", "info")
            return redirect(url_for("social.profile"))
        if outgoing.status == "declined":
            outgoing.status = "pending"
            outgoing.created_at = utcnow()
            db.session.commit()
            flash("Friend request sent again.", "success")
            return redirect(url_for("social.profile"))
        flash("You are already connected with that lifter.", "info")
        return redirect(url_for("social.profile"))

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
    return redirect(url_for("social.profile"))


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


@bp.route("/swipe", methods=["GET", "POST"])
@login_required
def swipe():
    if request.method == "POST":
        swipee_id = request.form.get("swipee_id", type=int)
        direction = (request.form.get("direction") or "").strip().lower()
        if swipee_id is None or direction not in ("left", "right"):
            flash("Invalid swipe.", "error")
            return redirect(url_for("social.swipe"))

        if swipee_id == current_user.id:
            flash("You cannot swipe on yourself.", "error")
            return redirect(url_for("social.swipe"))

        existing = Swipe.query.filter_by(swiper_id=current_user.id, swipee_id=swipee_id).first()
        if existing:
            flash("You already swiped this lifter.", "info")
            return redirect(url_for("social.swipe"))

        db.session.add(Swipe(swiper_id=current_user.id, swipee_id=swipee_id, direction=direction))
        if direction == "right":
            m = _try_create_match(current_user.id, swipee_id)
            if m:
                _finalize_friend_requests(current_user.id, swipee_id)
                from notification_helpers import mark_friend_requests_between_users_read

                mark_friend_requests_between_users_read(current_user.id, swipee_id)
                flash("It is a match! You are now gym friends.", "success")
            else:
                rev = FriendRequest.query.filter_by(
                    from_user_id=swipee_id,
                    to_user_id=current_user.id,
                    status="pending",
                ).first()
                if rev:
                    _ensure_match(current_user.id, swipee_id)
                    _finalize_friend_requests(current_user.id, swipee_id)
                    from notification_helpers import mark_friend_requests_between_users_read

                    mark_friend_requests_between_users_read(current_user.id, swipee_id)
                    flash("It is a match! You are now gym friends.", "success")
                else:
                    out = FriendRequest.query.filter_by(
                        from_user_id=current_user.id,
                        to_user_id=swipee_id,
                    ).first()
                    if not out:
                        fr = FriendRequest(
                            from_user_id=current_user.id,
                            to_user_id=swipee_id,
                            status="pending",
                            created_at=utcnow(),
                        )
                        db.session.add(fr)
                        db.session.flush()
                        from notification_helpers import notify_friend_request_created

                        notify_friend_request_created(fr)
                        flash("Friend request sent.", "success")
                    elif out.status == "pending":
                        flash("Friend request already pending.", "info")
                    elif out.status == "declined":
                        out.status = "pending"
                        out.created_at = utcnow()
                        db.session.flush()
                        from notification_helpers import notify_friend_request_created

                        notify_friend_request_created(out)
                        flash("Friend request sent again.", "success")
                    else:
                        flash("You are already connected with that lifter.", "info")
        else:
            flash("Skipped.", "info")
        db.session.commit()

        return redirect(url_for("social.swipe"))

    same_school = request.args.get("school") == "1"
    candidate = _next_swipe_candidate(
        current_user.id,
        same_school_only=same_school,
        school=(current_user.school or None),
        me=current_user,
    )
    return render_template(
        "swipe.html",
        candidate=candidate,
        same_school_only=same_school,
        has_school=bool(current_user.school),
    )


@bp.route("/matches/<int:match_id>", methods=["GET", "POST"])
@login_required
def match_thread(match_id: int):
    m = db.session.get(Match, match_id)
    if not m or current_user.id not in (m.user_a_id, m.user_b_id):
        abort(404)

    other_id = m.user_b_id if m.user_a_id == current_user.id else m.user_a_id
    other = db.session.get(User, other_id)

    if request.method == "POST":
        content = (request.form.get("content") or "").strip()
        if not content:
            flash("Message cannot be empty.", "error")
            return redirect(url_for("social.match_thread", match_id=match_id))
        msg = Message(match_id=m.id, sender_id=current_user.id, content=content, sent_at=utcnow())
        db.session.add(msg)
        db.session.commit()
        return redirect(url_for("social.match_thread", match_id=match_id))

    messages = (
        Message.query.filter_by(match_id=m.id).order_by(Message.sent_at.asc()).all()
    )
    return render_template(
        "match_thread.html",
        match=m,
        other=other,
        messages=messages,
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
    from workout_split_util import serialize_from_request

    current_user.school = (request.form.get("school") or "").strip() or None
    current_user.workout_split = serialize_from_request(request.form)
    db.session.commit()
    flash("School and split saved.", "success")
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

    connect_username = assign_username_if_missing(current_user)
    friend_connect_url = url_for(
        "social.connect_friend", username=connect_username, _external=True
    )
    qr_data = quote(friend_connect_url, safe="")

    goals = (
        Goal.query.filter_by(user_id=current_user.id)
        .order_by(Goal.completed.asc(), Goal.id.desc())
        .all()
    )
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

    from workout_split_util import card_lines, form_context

    _fc = form_context(current_user.workout_split)
    _lines, _legacy = card_lines(current_user.workout_split)

    return render_template(
        "profile.html",
        streak=streak,
        prs=prs,
        match_rows=match_rows,
        incoming_rows=incoming_rows,
        outgoing_rows=outgoing_rows,
        friend_connect_url=friend_connect_url,
        qr_data=qr_data,
        goals=goals,
        latest_weight=latest_w,
        suggested_friends=suggested,
        recent_workouts=recent_workouts,
        split_days=_fc["days"],
        split_display_lines=_lines,
        split_display_legacy=_legacy,
    )
