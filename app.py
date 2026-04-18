import os
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, request, send_from_directory, url_for
from flask_login import current_user, login_required, login_user
from flask_socketio import disconnect, join_room

from extensions import bcrypt, db, login_manager, socketio

_METERS_PER_MILE = 1609.344


def _demo_login_allowed(app: Flask) -> bool:
    """Passwordless /demo is off in production unless GYMLINK_ENABLE_DEMO_LOGIN is set."""
    if os.environ.get("GYMLINK_ENABLE_DEMO_LOGIN", "").lower() in ("1", "true", "yes"):
        return True
    if app.debug:
        return True
    if os.environ.get("RAILWAY_PUBLIC_DOMAIN") or os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        return False
    return True


def _gym_checkin_max_meters() -> float:
    """Radius for matching a seed/demo gym to the user's GPS fix (default 25 miles)."""
    raw_m = os.environ.get("GYM_CHECKIN_MAX_METERS")
    if raw_m is not None and str(raw_m).strip() != "":
        return float(raw_m)
    raw_mi = os.environ.get("GYM_CHECKIN_MAX_MILES")
    miles = 25.0
    if raw_mi is not None and str(raw_mi).strip() != "":
        miles = float(raw_mi)
    return miles * _METERS_PER_MILE


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or "gymlink-dev-secret-change-in-production"
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)

    db_uri = (os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if db_uri.startswith("postgres://"):
        db_uri = "postgresql://" + db_uri[len("postgres://") :]
    if not db_uri:
        db_uri = f"sqlite:///{instance_path / 'gymlink.db'}"
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    max_m = _gym_checkin_max_meters()
    app.config["GYM_CHECKIN_MAX_METERS"] = max_m
    app.config["GYM_CHECKIN_MAX_MILES"] = max_m / _METERS_PER_MILE
    app.config["UPLOAD_FOLDER"] = instance_path / "uploads"
    # Largest single-file uploads; multipart body must fit under max of these.
    app.config["MAX_PROFILE_PHOTO_BYTES"] = 25 * 1024 * 1024
    app.config["MAX_UPLOAD_IMAGE_BYTES"] = 25 * 1024 * 1024
    app.config["MAX_CONTENT_LENGTH"] = int(
        max(
            app.config["MAX_PROFILE_PHOTO_BYTES"],
            app.config["MAX_UPLOAD_IMAGE_BYTES"],
        )
    )
    app.config["OVERPASS_API_URL"] = os.environ.get(
        "OVERPASS_API_URL",
        "https://overpass-api.de/api/interpreter",
    )
    app.config["GYMLINK_HTTP_USER_AGENT"] = os.environ.get(
        "GYMLINK_HTTP_USER_AGENT",
        "GymLink/1.0 (gym check-in; contact your GymLink host)",
    )
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "").strip()
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587") or 587)
    app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "").strip()
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "").strip()
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", "").strip()

    if os.environ.get("RAILWAY_PUBLIC_DOMAIN") or os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        app.config["PREFERRED_URL_SCHEME"] = "https"
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.remember_cookie_duration = app.config["REMEMBER_COOKIE_DURATION"]
    bcrypt.init_app(app)
    socketio.init_app(app)

    from models import (  # noqa: F401
        CheckIn,
        DailyChallenge,
        DailyChallengeComplete,
        FriendFavorite,
        FriendGroup,
        FriendGroupMember,
        FriendRequest,
        GroupChallengeComplete,
        Goal,
        Gym,
        GroupMessage,
        Match,
        Message,
        Notification,
        OutdoorActivity,
        PasswordResetToken,
        PersonalRecord,
        Streak,
        Swipe,
        User,
        WeightLog,
        Workout,
    )

    from routes.account import bp as account_bp
    from routes.auth import bp as auth_bp
    from routes.gym import bp as gym_bp
    from routes.inbox import bp as inbox_bp
    from routes.leaderboard import bp as leaderboard_bp
    from routes.outdoor import bp as outdoor_bp
    from routes.social import bp as social_bp
    from routes.weights import bp as weights_bp
    from routes.workouts import bp as workouts_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(workouts_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(inbox_bp)
    app.register_blueprint(gym_bp)
    app.register_blueprint(outdoor_bp)
    app.register_blueprint(weights_bp)

    @app.get("/uploads/<path:name>")
    def uploaded_file(name: str):
        safe = Path(name).name
        if not safe:
            abort(404)
        folder = app.config["UPLOAD_FOLDER"]
        target = folder / safe
        if not target.is_file():
            abort(404)
        return send_from_directory(folder, safe)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.get("/demo")
    def demo_login():
        """One-click sign-in as the seeded demo user (local / explicit env only)."""
        if not _demo_login_allowed(app):
            abort(404)
        from models import User

        raw = (os.environ.get("GYMLINK_DEMO_USERNAME") or "jordan_blake").strip().lower()
        user = User.query.filter_by(username=raw).first()
        if not user:
            flash(
                "Demo user not found. Run `python seed.py` or set GYMLINK_DEMO_USERNAME to an existing username.",
                "error",
            )
            return redirect(url_for("auth.login"))
        login_user(user, remember=True)
        flash("Signed in as demo lifter — explore the leaderboard.", "info")
        return redirect(url_for("leaderboard.home"))

    @app.get("/")
    def root():
        if current_user.is_authenticated:
            return redirect(url_for("leaderboard.home"))
        return redirect(url_for("auth.login"))

    @app.get("/api/schools")
    def api_schools():
        """NCES IPEDS-backed institution name search (see static/data/us_institutions.json)."""
        from school_search import institution_count, search_institutions

        q = (request.args.get("q") or "").strip()
        try:
            limit = int(request.args.get("limit", 25))
        except ValueError:
            limit = 25
        return jsonify(
            {
                "results": search_institutions(q, limit),
                "total_loaded": institution_count(),
            }
        )

    @app.template_filter("school_badge")
    def school_badge_filter(user):
        if not user:
            return ""
        em = getattr(user, "school_email", None) or ""
        if "@" in em:
            return em.split("@", 1)[1][:64]
        return ""

    @app.template_filter("pacific")
    def pacific_dt_filter(value, fmt: str = "%b %d · %I:%M %p") -> str:
        """Format stored UTC datetimes for display in America/Los_Angeles."""
        from datetime import datetime as dtmod

        from pacific_display import pacific_strftime

        if value is None:
            return ""
        if isinstance(value, dtmod):
            return pacific_strftime(value, str(fmt))
        return ""

    @app.template_filter("media_url")
    def media_url_filter(path: str | None) -> str:
        """Resolve stored upload paths and external URLs for <img src> (feed, profile, etc.)."""
        if path is None:
            return ""
        p = str(path).strip()
        if not p:
            return ""
        if p.startswith("http://") or p.startswith("https://"):
            return p
        p = p.replace("\\", "/").strip()
        low = p.lower()
        if low.startswith("uploads/") and not low.startswith("/uploads/"):
            p = "/" + p
        # Bare filename only (legacy rows): treat as instance upload
        if not p.startswith("/") and "/" not in p:
            ext = Path(p).suffix.lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                p = "/uploads/" + Path(p).name
        if p.startswith("/uploads/"):
            safe = Path(p).name
            if safe and ".." not in p:
                return url_for("uploaded_file", name=safe)
            return ""
        return p

    @app.context_processor
    def inject_inbox_unread():
        try:
            if not current_user.is_authenticated:
                return {"inbox_unread_count": 0}
            from models import Notification

            c = Notification.query.filter_by(user_id=current_user.id, read_at=None).count()
            return {"inbox_unread_count": c}
        except Exception:
            return {"inbox_unread_count": 0}

    @app.context_processor
    def inject_exercise_preset_names():
        from exercise_presets import EXERCISE_PRESET_NAMES

        return {"exercise_preset_names": EXERCISE_PRESET_NAMES}

    @app.get("/api/me/workout-today")
    @login_required
    def api_workout_today():
        from workout_helpers import user_has_workout_on_date

        return jsonify({"logged": user_has_workout_on_date(current_user.id, date.today())})

    with app.app_context():
        db.create_all()
        _sqlite_add_missing_columns()
        _migrate_sqlite_username_column()

    return app


def _migrate_sqlite_username_column() -> None:
    """Add users.username on older SQLite DBs and backfill unique values."""
    import re

    from sqlalchemy import inspect, or_, text

    if db.engine.dialect.name != "sqlite":
        return
    insp = inspect(db.engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "username" not in cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(80)"))

    from models import User

    users = (
        User.query.filter(or_(User.username.is_(None), User.username == ""))
        .order_by(User.id)
        .all()
    )
    if not users:
        return

    for u in users:
        email = u.email or f"id{u.id}@local"
        base = email.split("@")[0].lower()
        base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
        if len(base) < 3:
            base = f"user{u.id}"
        base = base[:24]
        cand = base
        suffix = 0
        while True:
            clash = User.query.filter(User.username == cand, User.id != u.id).first()
            if not clash:
                break
            suffix += 1
            cand = f"{base}_{suffix}"[:30]
        u.username = cand
    db.session.commit()


def _sqlite_add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    if db.engine.dialect.name != "sqlite":
        return
    insp = inspect(db.engine)

    def add_col(table: str, col: str, ddl: str) -> None:
        if table not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns(table)}
        if col in cols:
            return
        with db.engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))

    add_col("users", "school", "VARCHAR(200)")
    add_col("users", "workout_split", "TEXT")
    add_col("workouts", "caption", "TEXT")
    add_col("workouts", "photo_path", "VARCHAR(512)")
    add_col("workouts", "is_pr_session", "INTEGER DEFAULT 0")
    add_col("gyms", "osm_key", "VARCHAR(32)")
    add_col("users", "school_email", "VARCHAR(255)")
    add_col("users", "home_gym_id", "INTEGER")
    add_col("users", "workout_days", "VARCHAR(64)")
    add_col("users", "goal_weight_lbs", "FLOAT")
    add_col("workouts", "is_rest_day", "INTEGER DEFAULT 0")
    add_col("users", "public_show_streak_stats", "INTEGER DEFAULT 1")
    add_col("users", "public_show_pr_highlights", "INTEGER DEFAULT 1")
    add_col("users", "public_show_profile_fields", "INTEGER DEFAULT 1")
    add_col("users", "public_weight_chart", "INTEGER DEFAULT 0")
    add_col("users", "public_workout_progress", "INTEGER DEFAULT 0")
    add_col("users", "reminder_hour", "INTEGER DEFAULT 8")
    add_col("users", "reminder_minute", "INTEGER DEFAULT 0")
    add_col("users", "current_body_weight_lbs", "FLOAT")
    add_col("matches", "user_a_last_read_at", "DATETIME")
    add_col("matches", "user_b_last_read_at", "DATETIME")
    add_col("workouts", "num_sets", "INTEGER")
    add_col("workouts", "duration_seconds", "INTEGER")
    add_col("workouts", "exercise_note", "TEXT")
    add_col("workouts", "split_weekday", "INTEGER")
    add_col("workouts", "off_plan", "INTEGER DEFAULT 0")
    add_col("workouts", "line_items", "TEXT")
    add_col("friend_groups", "challenge_title", "VARCHAR(200)")
    add_col("friend_groups", "challenge_day", "DATE")


app = create_app()


@socketio.on("connect")
def socket_connect():
    from flask import session

    uid = None
    if getattr(current_user, "is_authenticated", False):
        try:
            uid = int(current_user.get_id())
        except (TypeError, ValueError):
            uid = None
    if uid is None:
        raw = session.get("_user_id")
        if raw is not None:
            try:
                uid = int(raw)
            except (TypeError, ValueError):
                uid = None
    if uid is None:
        disconnect()
        return False
    join_room(f"user_{uid}")
    return True


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
