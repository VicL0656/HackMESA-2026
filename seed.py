"""Reset and seed the GymLink SQLite database with demo data.

Presenter account (`jordan_blake`) is gym friends with every other seeded lifter
plus Tom, with rich workouts/outdoors for Home, Feed, inbox, weight graph, and
daily challenge demos. Run: python seed.py
"""

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
    GroupChallengeComplete,
    GroupMessage,
    Gym,
    Match,
    Message,
    OutdoorActivity,
    PersonalRecord,
    Streak,
    User,
    WeightLog,
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

# Log in as this user to present Home, Feed, inbox, and friends with the full seeded crew.
PRESENTER_USERNAME = "jordan_blake"


def _ordered_user_ids(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _ensure_match(user_a_id: int, user_b_id: int, matched_at) -> None:
    lo, hi = _ordered_user_ids(user_a_id, user_b_id)
    if Match.query.filter_by(user_a_id=lo, user_b_id=hi).first():
        return
    db.session.add(Match(user_a_id=lo, user_b_id=hi, matched_at=matched_at))


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

        from tom_friend import TOM_USERNAME, befriend_tom, ensure_tom_user, get_tom_user

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
        presenter = next(u for u in users if u.username == PRESENTER_USERNAME)

        # Star topology: presenter is gym friends with every other seeded lifter (plus Tom via befriend_tom).
        for i, other in enumerate(users):
            if other.id == presenter.id:
                continue
            _ensure_match(presenter.id, other.id, now - timedelta(days=4 + (i % 55)))
        # Flush so Match rows are visible to later queries and to catch DB errors before heavy inserts.
        db.session.flush()

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

        lo_q, hi_q = _ordered_user_ids(presenter.id, users[6].id)
        mq = Match.query.filter_by(user_a_id=lo_q, user_b_id=hi_q).first()
        if mq:
            db.session.add(
                Message(
                    match_id=mq.id,
                    sender_id=users[6].id,
                    content="Free Saturday for a long squat session?",
                    sent_at=now - timedelta(hours=20),
                )
            )
            db.session.add(
                Message(
                    match_id=mq.id,
                    sender_id=presenter.id,
                    content="Yeah — ping me when you head to campus.",
                    sent_at=now - timedelta(hours=19),
                )
            )

        # --- Rich workouts (feed + journal): presenter + crew ---
        db.session.add(
            Workout(
                user_id=presenter.id,
                exercise_name="Bench Press",
                weight_lbs=225.0,
                reps=5,
                logged_at=now - timedelta(hours=2),
                caption="Heavy push — accessories after the big compounds.",
                photo_path=None,
                is_pr_session=False,
                num_sets=5,
                line_items=[
                    {"exercise_name": "Bench Press", "weight_lbs": 225, "reps": 5, "num_sets": 5},
                    {"exercise_name": "Overhead Press", "weight_lbs": 135, "reps": 8, "num_sets": 3},
                    {"exercise_name": "Tricep Pushdown", "weight_lbs": 50, "reps": 12, "num_sets": 3},
                ],
            )
        )
        db.session.add(
            Workout(
                user_id=presenter.id,
                exercise_name="Squat",
                weight_lbs=345.0,
                reps=5,
                logged_at=now - timedelta(days=1, hours=4),
                caption="High-bar triples — depth felt solid.",
                photo_path=None,
                is_pr_session=False,
                num_sets=4,
            )
        )
        db.session.add(
            Workout(
                user_id=presenter.id,
                exercise_name="Deadlift",
                weight_lbs=455.0,
                reps=1,
                logged_at=now - timedelta(days=4, hours=2),
                caption="Meet prep single — RPE 8.",
                photo_path=None,
                is_pr_session=True,
                num_sets=1,
            )
        )
        db.session.add(
            Workout(
                user_id=presenter.id,
                exercise_name="Rest day",
                weight_lbs=0.0,
                reps=1,
                logged_at=now - timedelta(days=3, hours=10),
                caption=None,
                photo_path=None,
                is_pr_session=False,
                is_rest_day=True,
            )
        )

        captions = [
            "Volume work then mobility.",
            "Light technique day.",
            "Posing practice after legs.",
            "EMOM finishers — legs toast.",
            "Deload week but still moving.",
        ]
        exercises_rotate = [
            ("Deadlift", 315, 3),
            ("Squat", 275, 5),
            ("Bench Press", 185, 8),
            ("Overhead Press", 115, 6),
            ("Romanian Deadlift", 225, 10),
        ]
        for idx, user in enumerate(users[1:], start=1):
            for j in range(3):
                ex, w, r = exercises_rotate[(idx + j) % len(exercises_rotate)]
                db.session.add(
                    Workout(
                        user_id=user.id,
                        exercise_name=ex,
                        weight_lbs=float(w - j * 5),
                        reps=r,
                        logged_at=now - timedelta(days=j * 2 + 1, hours=(idx + j) % 12),
                        caption=captions[(idx + j) % len(captions)] if j != 2 else None,
                        photo_path=None,
                        is_pr_session=bool(j == 0 and idx % 5 == 0),
                        num_sets=3 + j,
                    )
                )

        for idx in range(1, 11):
            u = users[idx]
            db.session.add(
                Workout(
                    user_id=u.id,
                    exercise_name="Pull Ups",
                    weight_lbs=float(pullup_base(idx)),
                    reps=8,
                    logged_at=now - timedelta(hours=6 + idx),
                    caption="Superset with rows.",
                    photo_path=None,
                    is_pr_session=False,
                )
            )

        db.session.add(
            Workout(
                user_id=users[1].id,
                exercise_name="Squat",
                weight_lbs=225.0,
                reps=6,
                logged_at=now - timedelta(hours=14),
                caption="Leg focus — controlled eccentrics.",
                photo_path=None,
                is_pr_session=False,
                num_sets=4,
                line_items=[
                    {"exercise_name": "Squat", "weight_lbs": 225, "reps": 6, "num_sets": 4},
                    {"exercise_name": "Leg Press", "weight_lbs": 410, "reps": 12, "num_sets": 3},
                ],
            )
        )

        # Today (UTC): several lifters logged so Home "daily challenge" panel looks alive.
        for idx in range(8):
            u = users[idx]
            db.session.add(
                Workout(
                    user_id=u.id,
                    exercise_name="Bench Press",
                    weight_lbs=float(bench_base(idx) - 5),
                    reps=5,
                    logged_at=now - timedelta(minutes=40 + idx * 6),
                    caption="Lunch session — quick bench and arms.",
                    photo_path=None,
                    is_pr_session=False,
                )
            )

        # --- Outdoor variety (feed) ---
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
        outdoor_more = [
            (3, "hike", "Trail ridge out-and-back", "Extra water — hot afternoon.", 4.5, 120.0, 4.5, "miles"),
            (4, "swim", "Pool: threshold 200s", "On the 3:00 send-off.", None, 45.0, 45.0, "minutes"),
            (5, "run", "Tempo six", "Progressive last two miles.", 6.0, 48.0, 6.0, "miles"),
            (6, "bike", "Commute plus hills", None, 12.0, 55.0, 12.0, "miles"),
            (7, "run", "Track repeats", "8×400, full recovery.", 4.0, 38.0, 4.0, "miles"),
            (8, "hike", "Sunday long", "Paced the climbs with a friend.", 8.0, 180.0, 8.0, "miles"),
            (9, "bike", "Recovery spin", "Zone 2 only.", 15.0, 50.0, 15.0, "miles"),
            (10, "run", "Shakeout jog", "Pre-meet legs.", 2.0, 18.0, 2.0, "miles"),
        ]
        for uid_idx, kind, title, notes, dist, dur, score, slabel in outdoor_more:
            db.session.add(
                OutdoorActivity(
                    user_id=users[uid_idx].id,
                    kind=kind,
                    title=title,
                    notes=notes,
                    distance_miles=dist,
                    duration_minutes=dur,
                    score=score,
                    score_label=slabel,
                    photo_path=None,
                    posted_at=now - timedelta(hours=14 + uid_idx),
                )
            )

        # --- Presenter account extras: weight graph, best friends, daily challenge ---
        presenter.current_body_weight_lbs = 184.2
        for day_off in range(1, 25):
            db.session.add(
                WeightLog(
                    user_id=presenter.id,
                    weight_lbs=185.0 - day_off * 0.12 + random.uniform(-0.45, 0.45),
                    logged_at=now - timedelta(days=day_off),
                    visibility="private",
                )
            )
        db.session.add(FriendFavorite(user_id=presenter.id, friend_user_id=users[1].id))
        db.session.add(FriendFavorite(user_id=presenter.id, friend_user_id=users[2].id))

        db.session.add(
            DailyChallenge(
                challenge_date=today,
                title="Log any workout or rest day",
                body="Seeded crew already logged — streaks and feed stay hot for demos.",
            )
        )
        db.session.add(
            DailyChallenge(
                challenge_date=yesterday,
                title="Move with intent",
                body="Yesterday's challenge row (seed).",
            )
        )
        for idx in range(8):
            db.session.add(
                DailyChallengeComplete(
                    user_id=users[idx].id,
                    challenge_date=today,
                    completed_at=now - timedelta(minutes=55 - idx * 3),
                )
            )

        from workout_helpers import recompute_streak_for_user

        for u in users:
            recompute_streak_for_user(u.id)
        tom_user = get_tom_user()
        if tom_user:
            recompute_streak_for_user(tom_user.id)

        from sqlalchemy import or_

        tom_check = get_tom_user()
        if not tom_check:
            raise RuntimeError("Seed: Tom user missing after ensure_tom_user / befriend_tom.")
        pid = presenter.id
        presenter_match_count = Match.query.filter(
            or_(Match.user_a_id == pid, Match.user_b_id == pid),
        ).count()
        want_presenter_edges = len(users)  # 19 other seed lifters + Tom
        if presenter_match_count < want_presenter_edges:
            raise RuntimeError(
                f"Seed: presenter @{presenter.username} has {presenter_match_count} match rows, "
                f"expected at least {want_presenter_edges} (every other seed user + Tom). "
                "Re-run this seed on a clean DB, or run scripts/backfill_presenter_demo_graph.py."
            )

        db.session.commit()
        print("Seed complete.")
        print(
            f"Presenter (full friends + feed): {PRESENTER_USERNAME} / jordan.blake@gymlink.demo - password: password123"
        )
        print(f"Any other seeded user: password password123 (see USERS in seed.py).")
        print(f"Default friend Tom: username {TOM_USERNAME}, password: password123")
        print("Gym check-in: uses your location + OpenStreetMap (no fixed demo city).")


if __name__ == "__main__":
    main()
