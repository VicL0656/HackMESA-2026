from pathlib import Path

from flask import Flask, redirect, url_for
from flask_login import current_user
from flask_socketio import disconnect, join_room

from extensions import bcrypt, db, login_manager, socketio


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    app.config["SECRET_KEY"] = "gymlink-dev-secret-change-in-production"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{instance_path / 'gymlink.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    socketio.init_app(app)

    from models import CheckIn, Gym, Match, Message, PersonalRecord, Streak, Swipe, User, Workout  # noqa: F401

    from routes.auth import bp as auth_bp
    from routes.gym import bp as gym_bp
    from routes.leaderboard import bp as leaderboard_bp
    from routes.social import bp as social_bp
    from routes.workouts import bp as workouts_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(workouts_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(gym_bp)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def root():
        if current_user.is_authenticated:
            return redirect(url_for("leaderboard.home"))
        return redirect(url_for("auth.login"))

    return app


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
