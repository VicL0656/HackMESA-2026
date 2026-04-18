from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from extensions import db, login_manager


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    photo_url = db.Column(db.String(512), nullable=True)
    workout_style = db.Column(db.String(64), nullable=True)
    goals = db.Column(db.String(512), nullable=True)
    school = db.Column(db.String(200), nullable=True, index=True)
    school_email = db.Column(db.String(255), nullable=True, index=True)
    workout_split = db.Column(db.Text, nullable=True)
    home_gym_id = db.Column(db.Integer, db.ForeignKey("gyms.id"), nullable=True, index=True)
    workout_days = db.Column(db.String(64), nullable=True)  # JSON list of weekday ints 0=Mon..6=Sun
    goal_weight_lbs = db.Column(db.Float, nullable=True)
    # SHA-256 hex of server secret + token (see health_bridge_auth); for Shortcuts / Health automations only.
    health_bridge_token_hash = db.Column(db.String(128), nullable=True, unique=True, index=True)

    home_gym = db.relationship("Gym", foreign_keys=[home_gym_id])

    check_ins = db.relationship("CheckIn", backref="user", lazy="dynamic")
    workouts = db.relationship("Workout", backref="user", lazy="dynamic")
    weight_logs = db.relationship("WeightLog", backref="user", lazy="dynamic")
    goals_rel = db.relationship("Goal", backref="user", lazy="dynamic")
    personal_records = db.relationship("PersonalRecord", backref="user", lazy="dynamic")
    streak_row = db.relationship(
        "Streak",
        backref="user",
        uselist=False,
        lazy="joined",
    )

    swipes_sent = db.relationship(
        "Swipe",
        foreign_keys="Swipe.swiper_id",
        backref="swiper",
        lazy="dynamic",
    )
    swipes_received = db.relationship(
        "Swipe",
        foreign_keys="Swipe.swipee_id",
        backref="swipee",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<User @{self.username}>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Gym(db.Model):
    __tablename__ = "gyms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    # OpenStreetMap element key, e.g. "n/123" or "w/456" — null for manually added rows
    osm_key = db.Column(db.String(32), nullable=True, unique=True, index=True)

    check_ins = db.relationship("CheckIn", backref="gym", lazy="dynamic")


class CheckIn(db.Model):
    __tablename__ = "check_ins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    gym_id = db.Column(db.Integer, db.ForeignKey("gyms.id"), nullable=False, index=True)
    checked_in_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    checked_out_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (Index("ix_check_ins_user_active", "user_id", "checked_out_at"),)


class Swipe(db.Model):
    __tablename__ = "swipes"

    id = db.Column(db.Integer, primary_key=True)
    swiper_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    swipee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)

    __table_args__ = (
        UniqueConstraint("swiper_id", "swipee_id", name="uq_swipe_pair"),
        CheckConstraint("direction IN ('left','right')", name="ck_swipe_direction"),
        CheckConstraint("swiper_id != swipee_id", name="ck_swipe_not_self"),
    )


class FriendRequest(db.Model):
    __tablename__ = "friend_requests"

    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    sender = db.relationship("User", foreign_keys=[from_user_id])

    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_friend_request_pair"),
        CheckConstraint("from_user_id != to_user_id", name="ck_friend_request_not_self"),
        CheckConstraint("status IN ('pending','accepted','declined')", name="ck_friend_request_status"),
    )


class Match(db.Model):
    __tablename__ = "matches"

    id = db.Column(db.Integer, primary_key=True)
    user_a_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user_b_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    matched_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user_a = db.relationship("User", foreign_keys=[user_a_id])
    user_b = db.relationship("User", foreign_keys=[user_b_id])
    messages = db.relationship("Message", backref="match", lazy="dynamic")

    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_match_pair"),
        CheckConstraint("user_a_id < user_b_id", name="ck_match_ordered_ids"),
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    sender = db.relationship("User", foreign_keys=[sender_id])


class Workout(db.Model):
    __tablename__ = "workouts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    exercise_name = db.Column(db.String(120), nullable=False, index=True)
    weight_lbs = db.Column(db.Float, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    logged_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    caption = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(512), nullable=True)
    is_pr_session = db.Column(db.Boolean, nullable=False, default=False)
    is_rest_day = db.Column(db.Boolean, nullable=False, default=False)


class WeightLog(db.Model):
    __tablename__ = "weight_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    weight_lbs = db.Column(db.Float, nullable=False)
    logged_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    visibility = db.Column(db.String(20), nullable=False, default="friends")

    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public','friends','private')",
            name="ck_weightlog_visibility",
        ),
    )


class Goal(db.Model):
    __tablename__ = "goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    target_value = db.Column(db.Float, nullable=False)
    current_value = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(40), nullable=False, default="")
    deadline = db.Column(db.Date, nullable=True)
    completed = db.Column(db.Boolean, nullable=False, default=False)


class OutdoorActivity(db.Model):
    __tablename__ = "outdoor_activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    distance_miles = db.Column(db.Float, nullable=True)
    duration_minutes = db.Column(db.Float, nullable=True)
    score = db.Column(db.Float, nullable=False)
    score_label = db.Column(db.String(40), nullable=True)
    photo_path = db.Column(db.String(512), nullable=True)
    posted_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", backref="outdoor_activities")

    __table_args__ = (
        CheckConstraint("kind IN ('run','bike','hike','swim','other')", name="ck_outdoor_kind"),
    )


class PersonalRecord(db.Model):
    __tablename__ = "personal_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    exercise_name = db.Column(db.String(120), nullable=False, index=True)
    best_weight_lbs = db.Column(db.Float, nullable=False)
    best_reps = db.Column(db.Integer, nullable=False)
    achieved_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "exercise_name", name="uq_pr_user_exercise"),)


class Streak(db.Model):
    __tablename__ = "streaks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    current_streak = db.Column(db.Integer, nullable=False, default=0)
    longest_streak = db.Column(db.Integer, nullable=False, default=0)
    last_logged_date = db.Column(db.Date, nullable=True)


class Notification(db.Model):
    """In-app inbox row for a single user."""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=True)
    action_url = db.Column(db.String(512), nullable=True)
    priority = db.Column(db.Boolean, nullable=False, default=True)
    read_at = db.Column(db.DateTime, nullable=True)
    dedupe_key = db.Column(db.String(140), nullable=True, index=True)
    friend_request_id = db.Column(db.Integer, db.ForeignKey("friend_requests.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notification_user_dedupe"),
        CheckConstraint(
            "kind IN ('friend_request','friend_pr','streak_risk','system')",
            name="ck_notification_kind",
        ),
    )


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
