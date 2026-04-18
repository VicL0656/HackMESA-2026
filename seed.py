"""Reset and seed the GymLink SQLite database with demo data."""

from __future__ import annotations

import random
from datetime import date, timedelta

from app import app
from extensions import bcrypt, db
from models import FriendRequest  # noqa: F401 — registers friend_requests table for drop_all/create_all
from models import (
    DailyChallenge,
    DailyChallengeComplete,
    FriendFavorite,
    FriendGroup,
    FriendGroupMember,
    GroupMessage,
    Gym,
    Match,
    Message,
    OutdoorActivity,
    PersonalRecord,
    Streak,
    User,
    Workout,
    utcnow,
)

EXERCISES = ["Bench Press", "Squat", "Deadlift", "Overhead Press", "Pull Ups"]

DEMO_SCHOOL = "Indiana University"
DEMO_SPLIT = (
    '{"version":1,"days":['
    '{"upper":true,"lower":false,"other":false,"other_text":""},'
    '{"upper":false,"lower":true,"other":false,"other_text":""},'
    '{"upper":false,"lower":false,"other":true,"other_text":"Legs"},'
    '{"upper":true,"lower":false,"other":true,"other_text":"Cardio"},'
    '{"upper":false,"lower":true,"other":false,"other_text":""},'
    '{"upper":false,"lower":false,"other":true,"other_text":"Active recovery"},'
    '{"upper":false,"lower":false,"other":false,"other_text":""}'
    ']}'
)

# Real gyms are resolved at check-in from the user's GPS + OpenStreetMap (see routes/gym.py).
GYMS: list[dict] = []

USERS = [
    ("Jordan Blake", "jordan_blake", "jordan.blake@gymlink.demo", "powerlifting", "Qualify for a collegiate meet this spring."),
    ("Mia Chen", "mia_chen", "mia.chen@gymlink.demo", "bodybuilding", "Bring up shoulders while staying stage lean."),
    ("Noah Patel", "noah_patel", "noah.patel@gymlink.demo", "crossfit", "Sub-3 Fran and better handstand walks."),
    ("Avery Johnson", "avery_j", "avery.johnson@gymlink.demo", "cardio", "Run a half marathon under 1:45."),
    ("Riley Martinez", "riley_m", "riley.martinez@gymlink.demo", "powerlifting", "Hit a 500 lb deadlift before finals."),
    ("Taylor Brooks", "taylor_brooks", "taylor.brooks@gymlink.demo", "bodybuilding", "Grow legs without losing abs."),
    ("Casey Nguyen", "casey_n", "casey.nguyen@gymlink.demo", "crossfit", "Improve ring muscle-ups for the Open."),
    ("Quinn Rivera", "quinn_r", "quinn.rivera@gymlink.demo", "powerlifting", "Fix squat depth and stay healthy."),
    ("Skyler Adams", "skyler_adams", "skyler.adams@gymlink.demo", "cardio", "Row 5k three mornings a week."),
    ("Reese Thompson", "reese_t", "reese.thompson@gymlink.demo", "bodybuilding", "Dial in posing for summer."),
    ("Jamie Foster", "jamie_foster", "jamie.foster@gymlink.demo", "crossfit", "String together double-unders in WODs."),
    ("Cameron Lee", "cameron_lee", "cameron.lee@gymlink.demo", "powerlifting", "Bench 315 with competition pause."),
    ("Logan Wright", "logan_w", "logan.wright@gymlink.demo", "bodybuilding", "Lean bulk through the semester."),
    ("Harper Scott", "harper_scott", "harper.scott@gymlink.demo", "cardio", "Bike commute + two tempo sessions weekly."),
    ("Parker Evans", "parker_e", "parker.evans@gymlink.demo", "crossfit", "Improve Olympic total by 15 kg."),
    ("Emerson Hill", "emerson_hill", "emerson.hill@gymlink.demo", "powerlifting", "Perfect sumo technique on heavy singles."),
    ("Finley Green", "finley_g", "finley.green@gymlink.demo", "bodybuilding", "Bring hamstrings up to match quads."),
    ("Drew Collins", "drew_collins", "drew.collins@gymlink.demo", "crossfit", "Work on strict handstand push-ups."),
    ("Blake Turner", "blake_turner", "blake.turner@gymlink.demo", "cardio", "Track VO2 improvements month to month."),
    ("Sydney Reed", "sydney_reed", "sydney.reed@gymlink.demo", "powerlifting", "Compete at collegiate nationals."),
]


def bench_base(idx: int) -> float:
    return 155 + (idx * 7) % 120


def squat_base(idx: int) -> float:
    return 185 + (idx * 11) % 140


def deadlift_base(idx: int) -> float:
    return 225 + (idx * 13) % 160


def ohp_base(idx: int) -> float:
    return 95 + (idx * 5) % 55


def pullup_base(idx: int) -> float:
    return 25 + (idx * 3) % 40


def pr_tuple(idx: int, exercise: str):
    if exercise == "Bench Press":
        w = bench_base(idx)
    elif exercise == "Squat":
        w = squat_base(idx)
    elif exercise == "Deadlift":
        w = deadlift_base(idx)
    elif exercise == "Overhead Press":
        w = ohp_base(idx)
    else:
        w = pullup_base(idx)
    reps = 3 + (idx + len(exercise)) % 5
    return float(w), int(reps)


def main() -> None:
    random.seed(42)
    with app.app_context():
        db.drop_all()
        db.create_all()

        gyms = []
        for g in GYMS:
            gym = Gym(
                name=g["name"],
                address=g["address"],
                latitude=g["latitude"],
                longitude=g["longitude"],
                osm_key=g.get("osm_key"),
            )
            db.session.add(gym)
            gyms.append(gym)
        db.session.flush()
        password_hash = bcrypt.generate_password_hash("password123")
        if isinstance(password_hash, bytes):
            password_hash = password_hash.decode("utf-8")

        users: list[User] = []
        for idx, (name, username, email, style, goals) in enumerate(USERS):
            user = User(
                name=name,
                username=username,
                email=email,
                password_hash=password_hash,
                photo_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={username}",
                workout_style=style,
                goals=goals,
                school=DEMO_SCHOOL,
                workout_split=DEMO_SPLIT,
            )
            db.session.add(user)
            users.append(user)
        db.session.flush()

        from tom_friend import TOM_USERNAME, befriend_tom, ensure_tom_user

        ensure_tom_user()
        db.session.flush()
        for u in users:
            befriend_tom(u.id)

        today = date.today()
        yesterday = today - timedelta(days=1)

        for idx, user in enumerate(users):
            streak_days = 3 + (idx * 2) % 19
            last_logged = yesterday if idx % 3 else today
            longest = max(streak_days, streak_days + (idx % 4))
            db.session.add(
                Streak(
                    user_id=user.id,
                    current_streak=streak_days,
                    longest_streak=longest,
                    last_logged_date=last_logged,
                )
            )

        for idx, user in enumerate(users):
            for exercise in EXERCISES:
                weight, reps = pr_tuple(idx, exercise)
                db.session.add(
                    PersonalRecord(
                        user_id=user.id,
                        exercise_name=exercise,
                        best_weight_lbs=weight,
                        best_reps=reps,
                        achieved_at=utcnow() - timedelta(days=random.randint(1, 40)),
                    )
                )

        for i in range(0, len(users), 2):
            u1, u2 = users[i], users[i + 1]
            low, high = sorted([u1.id, u2.id])
            db.session.add(
                Match(
                    user_a_id=low,
                    user_b_id=high,
                    matched_at=utcnow() - timedelta(days=random.randint(2, 30)),
                )
            )

        db.session.flush()

        now = utcnow()
        low, high = sorted([users[0].id, users[1].id])
        m0 = Match.query.filter_by(user_a_id=low, user_b_id=high).first()
        if m0:
            db.session.add(
                Message(
                    match_id=m0.id,
                    sender_id=users[0].id,
                    content="Leg day tomorrow?",
                    sent_at=now - timedelta(hours=3),
                )
            )
            db.session.add(
                Message(
                    match_id=m0.id,
                    sender_id=users[1].id,
                    content="Yes — meet you at the gym at 7.",
                    sent_at=now - timedelta(hours=2),
                )
            )

        for idx, user in enumerate(users[:6]):
            db.session.add(
                Workout(
                    user_id=user.id,
                    exercise_name="Bench Press",
                    weight_lbs=bench_base(idx) - 10,
                    reps=5,
                    logged_at=now - timedelta(hours=random.randint(1, 36)),
                    caption="Volume bench day — chasing a smooth competition pause.",
                    photo_path=None,
                    is_pr_session=False,
                )
            )

        db.session.add(
            OutdoorActivity(
                user_id=users[0].id,
                kind="run",
                title="Campus loop tempo",
                notes="Negative split on the second half.",
                distance_miles=5.2,
                duration_minutes=41.0,
                score=5.2,
                score_label="miles",
                photo_path=None,
                posted_at=now - timedelta(hours=5),
            )
        )
        db.session.add(
            OutdoorActivity(
                user_id=users[1].id,
                kind="bike",
                title="Rail trail cruise",
                notes="Easy spin with a few hard pickups.",
                distance_miles=22.0,
                duration_minutes=88.0,
                score=22.0,
                score_label="miles",
                photo_path=None,
                posted_at=now - timedelta(hours=8),
            )
        )
        db.session.add(
            OutdoorActivity(
                user_id=users[2].id,
                kind="run",
                title="Morning 5K test",
                notes="Felt smooth, pushed last mile.",
                distance_miles=3.1,
                duration_minutes=22.5,
                score=3.1,
                score_label="miles",
                photo_path=None,
                posted_at=now - timedelta(hours=12),
            )
        )

        db.session.commit()
        print("Seed complete.")
        print(f"Demo login (any user): email from seed list, password: password123")
        print(f"Default friend Tom: username {TOM_USERNAME}, password: password123")
        print("Gym check-in: uses your location + OpenStreetMap (no fixed demo city).")


if __name__ == "__main__":
    main()
