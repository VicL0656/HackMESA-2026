"""
GymLink's default friend (Myspace-style): everyone gets a match with Tom on register/login.

Tom uses a reserved username and internal-only email so real users cannot register the same handle.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from extensions import bcrypt, db
from models import Goal, Match, Message, PersonalRecord, Streak, User, Workout
from models import utcnow

TOM_USERNAME = "gymlink_tom"
TOM_EMAIL = "tom+system@gymlink.invalid"
TOM_DISPLAY_NAME = "Tom"
TOM_WELCOME = (
    "Hey — I'm Tom, your first gym friend here. "
    "Log a workout, say hi in chat anytime, and add friends from Home or suggested lifters. "
    "Welcome to GymLink!"
)

_TOM_SPLIT = json.dumps(
    {
        "version": 1,
        "days": [
            {"upper": True, "lower": False, "other": False, "other_text": ""},
            {"upper": False, "lower": True, "other": False, "other_text": ""},
            {"upper": False, "lower": False, "other": True, "other_text": "Cardio"},
            {"upper": True, "lower": False, "other": False, "other_text": ""},
            {"upper": False, "lower": True, "other": False, "other_text": ""},
            {"upper": False, "lower": False, "other": True, "other_text": "Active recovery"},
            {"upper": False, "lower": False, "other": False, "other_text": ""},
        ],
    },
    separators=(",", ":"),
)


def _ordered_pair(a_id: int, b_id: int) -> tuple[int, int]:
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


def is_reserved_username(normalized_username: str | None) -> bool:
    if not normalized_username:
        return False
    return normalized_username.strip().lower() == TOM_USERNAME


def is_tom_user(user: User | None) -> bool:
    if not user:
        return False
    return (getattr(user, "username", None) or "").strip().lower() == TOM_USERNAME


def get_tom_user() -> User | None:
    return User.query.filter_by(username=TOM_USERNAME).first()


def ensure_tom_user() -> User:
    """Create Tom with demo lifts if missing. Does not commit."""
    existing = get_tom_user()
    if existing:
        return existing

    pw = bcrypt.generate_password_hash("password123")
    if isinstance(pw, bytes):
        pw = pw.decode("utf-8")
    tom = User(
        name=TOM_DISPLAY_NAME,
        username=TOM_USERNAME,
        email=TOM_EMAIL,
        password_hash=pw,
        photo_url="https://api.dicebear.com/7.x/avataaars/svg?seed=gymlink-tom",
        workout_style="Everyone's first friend",
        goals="Here to cheer on your first PRs and streaks.",
        school="GymLink",
        workout_split=_TOM_SPLIT,
    )
    db.session.add(tom)
    db.session.flush()

    today = date.today()
    db.session.add(
        Streak(
            user_id=tom.id,
            current_streak=42,
            longest_streak=100,
            last_logged_date=today,
        )
    )
    now = utcnow()
    for ex, w, r in (
        ("Bench Press", 225.0, 3),
        ("Squat", 315.0, 5),
        ("Deadlift", 405.0, 1),
        ("Pull Ups", 25.0, 10),
    ):
        db.session.add(
            PersonalRecord(
                user_id=tom.id,
                exercise_name=ex,
                best_weight_lbs=w,
                best_reps=r,
                achieved_at=now - timedelta(days=14),
            )
        )
    for i, (ex, w, r, cap) in enumerate(
        [
            ("Bench Press", 185.0, 8, "Smooth triples — saving the heavy singles for meet prep."),
            ("Squat", 275.0, 5, "High-bar, ATG. Legs are feeling strong this block."),
            ("Deadlift", 365.0, 3, "Conventional, mixed grip. Film from the side next time."),
            ("Overhead Press", 135.0, 6, "Strict press, no leg drive. Shoulders are catching up."),
        ]
    ):
        db.session.add(
            Workout(
                user_id=tom.id,
                exercise_name=ex,
                weight_lbs=w,
                reps=r,
                logged_at=now - timedelta(days=i + 1, hours=4),
                caption=cap,
                photo_path=None,
                is_pr_session=False,
                is_rest_day=False,
            )
        )
    db.session.add(
        Goal(
            user_id=tom.id,
            title="Help 10,000 lifters log their first week",
            target_value=10000.0,
            current_value=1247.0,
            unit="lifters",
            deadline=None,
            completed=False,
        )
    )
    db.session.flush()
    return tom


def befriend_tom(user_id: int) -> None:
    """Create a gym-friend match + welcome DM if not already friends. Does not commit."""
    tom = get_tom_user()
    if not tom or tom.id == user_id:
        return
    lo, hi = _ordered_pair(user_id, tom.id)
    if Match.query.filter_by(user_a_id=lo, user_b_id=hi).first():
        return
    m = Match(user_a_id=lo, user_b_id=hi, matched_at=utcnow())
    db.session.add(m)
    db.session.flush()
    db.session.add(
        Message(
            match_id=m.id,
            sender_id=tom.id,
            content=TOM_WELCOME,
            sent_at=utcnow(),
        )
    )
