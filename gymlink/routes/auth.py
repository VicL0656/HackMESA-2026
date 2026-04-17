from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from extensions import bcrypt, db
from models import Streak, User

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("leaderboard.home"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        workout_style = (request.form.get("workout_style") or "").strip()
        goals = (request.form.get("goals") or "").strip()

        if not name or not email or len(password) < 8:
            flash("Please provide name, email, and a password of at least 8 characters.", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
            return render_template("register.html")

        pw_hash = bcrypt.generate_password_hash(password)
        if isinstance(pw_hash, bytes):
            pw_hash = pw_hash.decode("utf-8")
        user = User(
            name=name,
            email=email,
            password_hash=pw_hash,
            workout_style=workout_style or None,
            goals=goals or None,
            photo_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={email}",
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(Streak(user_id=user.id, current_streak=0, longest_streak=0, last_logged_date=None))
        db.session.commit()
        login_user(user)
        flash("Welcome to GymLink!", "success")
        return redirect(url_for("leaderboard.home"))

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("leaderboard.home"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if not user or not bcrypt.check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")
        login_user(user)
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("leaderboard.home"))

    return render_template("login.html")


@bp.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
