from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Match, Message, Swipe, User, Workout
from models import utcnow

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


def _next_swipe_candidate(user_id: int):
    matched = _matched_user_ids(user_id)
    swiped = _swiped_user_ids(user_id)
    candidates = (
        User.query.filter(User.id != user_id)
        .order_by(User.id)
        .all()
    )
    for u in candidates:
        if u.id in matched or u.id in swiped:
            continue
        return u
    return None


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


@bp.route("/feed")
@login_required
def feed():
    friend_ids = list(_friend_ids(current_user.id))
    workouts = []
    if friend_ids:
        workouts = (
            Workout.query.filter(Workout.user_id.in_(friend_ids))
            .order_by(Workout.logged_at.desc())
            .limit(20)
            .all()
        )
    users_by_id = {u.id: u for u in User.query.filter(User.id.in_(friend_ids)).all()} if friend_ids else {}
    return render_template(
        "feed.html",
        friend_workouts=workouts,
        users_by_id=users_by_id,
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
                flash("It is a match! You are now gym friends.", "success")
            else:
                flash("Friend request sent.", "success")
        else:
            flash("Skipped.", "info")
        db.session.commit()

        return redirect(url_for("social.swipe"))

    candidate = _next_swipe_candidate(current_user.id)
    return render_template("swipe.html", candidate=candidate)


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
    return render_template(
        "profile.html",
        streak=streak,
        prs=prs,
        match_rows=match_rows,
    )
