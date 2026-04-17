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
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    photo_url = db.Column(db.String(512), nullable=True)
    workout_style = db.Column(db.String(64), nullable=True)
    goals = db.Column(db.String(512), nullable=True)

    check_ins = db.relationship("CheckIn", backref="user", lazy="dynamic")
    workouts = db.relationship("Workout", backref="user", lazy="dynamic")
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
        return f"<User {self.email}>"


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
