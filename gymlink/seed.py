"""Reset and seed the GymLink SQLite database with demo data."""

from __future__ import annotations

import random
from datetime import date, timedelta

from app import app
from extensions import bcrypt, db
from models import (
    CheckIn,
    Gym,
    Match,
    Message,
    PersonalRecord,
    Streak,
    User,
    Workout,
    utcnow,
)

EXERCISES = ["Bench Press", "Squat", "Deadlift", "Overhead Press", "Pull Ups"]

GYMS = [
    {
        "name": "Iron Campus Barbell",
        "address": "401 E Kirkwood Ave, Bloomington, IN",
        "latitude": 39.16641,
        "longitude": -86.52812,
    },
    {
        "name": "Hoosier Strength Lab",
        "address": "222 N Walnut St, Bloomington, IN",
        "latitude": 39.16725,
        "longitude": -86.53355,
    },
    {
        "name": "Cardio Loft B-Town",
        "address": "812 N Dunn St, Bloomington, IN",
        "latitude": 39.17105,
        "longitude": -86.52418,
    },
    {
        "name": "Sample Gates Athletic Club",
        "address": "501 N Indiana Ave, Bloomington, IN",
        "latitude": 39.16512,
        "longitude": -86.5252,
    },
    {
        "name": "Kettle Collective Row House",
        "address": "910 W 4th St, Bloomington, IN",
        "latitude": 39.16238,
        "longitude": -86.5411,
    },
]

USERS = [
    ("Jordan Blake", "jordan.blake@gymlink.demo", "powerlifting", "Qualify for a collegiate meet this spring."),
    ("Mia Chen", "mia.chen@gymlink.demo", "bodybuilding", "Bring up shoulders while staying stage lean."),
    ("Noah Patel", "noah.patel@gymlink.demo", "crossfit", "Sub-3 Fran and better handstand walks."),
    ("Avery Johnson", "avery.johnson@gymlink.demo", "cardio", "Run a half marathon under 1:45."),
    ("Riley Martinez", "riley.martinez@gymlink.demo", "powerlifting", "Hit a 500 lb deadlift before finals."),
    ("Taylor Brooks", "taylor.brooks@gymlink.demo", "bodybuilding", "Grow legs without losing abs."),
    ("Casey Nguyen", "casey.nguyen@gymlink.demo", "crossfit", "Improve ring muscle-ups for the Open."),
    ("Quinn Rivera", "quinn.rivera@gymlink.demo", "powerlifting", "Fix squat depth and stay healthy."),
    ("Skyler Adams", "skyler.adams@gymlink.demo", "cardio", "Row 5k three mornings a week."),
    ("Reese Thompson", "reese.thompson@gymlink.demo", "bodybuilding", "Dial in posing for summer."),
    ("Jamie Foster", "jamie.foster@gymlink.demo", "crossfit", "String together double-unders in WODs."),
    ("Cameron Lee", "cameron.lee@gymlink.demo", "powerlifting", "Bench 315 with competition pause."),
    ("Logan Wright", "logan.wright@gymlink.demo", "bodybuilding", "Lean bulk through the semester."),
    ("Harper Scott", "harper.scott@gymlink.demo", "cardio", "Bike commute + two tempo sessions weekly."),
    ("Parker Evans", "parker.evans@gymlink.demo", "crossfit", "Improve Olympic total by 15 kg."),
    ("Emerson Hill", "emerson.hill@gymlink.demo", "powerlifting", "Perfect sumo technique on heavy singles."),
    ("Finley Green", "finley.green@gymlink.demo", "bodybuilding", "Bring hamstrings up to match quads."),
    ("Drew Collins", "drew.collins@gymlink.demo", "crossfit", "Work on strict handstand push-ups."),
    ("Blake Turner", "blake.turner@gymlink.demo", "cardio", "Track VO2 improvements month to month."),
    ("Sydney Reed", "sydney.reed@gymlink.demo", "powerlifting", "Compete at collegiate nationals."),
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
            gym = Gym(name=g["name"], address=g["address"], latitude=g["latitude"], longitude=g["longitude"])
            db.session.add(gym)
            gyms.append(gym)
        db.session.flush()

        demo_gym = gyms[0]
        password_hash = bcrypt.generate_password_hash("password123")
        if isinstance(password_hash, bytes):
            password_hash = password_hash.decode("utf-8")

        users: list[User] = []
        for idx, (name, email, style, goals) in enumerate(USERS):
            user = User(
                name=name,
                email=email,
                password_hash=password_hash,
                photo_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={email}",
                workout_style=style,
                goals=goals,
            )
            db.session.add(user)
            users.append(user)
        db.session.flush()

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
                    content="Yes — meet you at Iron Campus at 7.",
                    sent_at=now - timedelta(hours=2),
                )
            )

        for user in users[:8]:
            db.session.add(
                CheckIn(
                    user_id=user.id,
                    gym_id=demo_gym.id,
                    checked_in_at=now - timedelta(minutes=random.randint(5, 120)),
                    checked_out_at=None,
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
                )
            )

        db.session.commit()
        print("Seed complete.")
        print(f"Demo login (any user): email from seed list, password: password123")
        print(f"Primary demo gym for check-ins: {demo_gym.name} near {demo_gym.latitude}, {demo_gym.longitude}")


if __name__ == "__main__":
    main()
