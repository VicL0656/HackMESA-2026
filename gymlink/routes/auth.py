from __future__ import annotations

import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from extensions import bcrypt, db
from models import Streak, User
from username_utils import USERNAME_RE, normalize_username, resolve_user_by_email_or_username

bp = Blueprint("auth", __name__)

_EDU = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu$")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("leaderboard.home"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        username_raw = (request.form.get("username") or "").strip()
        username = normalize_username(username_raw)
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        workout_style = (request.form.get("workout_style") or "").strip()
        goals = (request.form.get("goals") or "").strip()
        school = (request.form.get("school") or "").strip() or None
        school_email = (request.form.get("school_email") or "").strip().lower() or None
        if school_email and not _EDU.match(school_email):
            flash("School email must be a valid .edu address, or leave it blank.", "error")
            return render_template("register.html")

        if not name or not email or len(password) < 8:
            flash("Please provide name, email, and a password of at least 8 characters.", "error")
            return render_template("register.html")

        if not username or not USERNAME_RE.match(username):
            flash("Username must be 3–30 characters: lowercase letters, numbers, and underscores only.", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
            return render_template("register.html")

        pw_hash = bcrypt.generate_password_hash(password)
        if isinstance(pw_hash, bytes):
            pw_hash = pw_hash.decode("utf-8")
        user = User(
            name=name,
            username=username,
            email=email,
            password_hash=pw_hash,
            workout_style=workout_style or None,
            goals=goals or None,
            school=school,
            school_email=school_email,
            photo_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={username}",
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(Streak(user_id=user.id, current_streak=0, longest_streak=0, last_logged_date=None))
        db.session.commit()
        remember = bool(request.form.get("remember"))
        login_user(user, remember=remember)
        flash("Welcome to GymLink!", "success")
        return redirect(url_for("leaderboard.home"))

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("leaderboard.home"))

    if request.method == "POST":
        ident = (request.form.get("identifier") or request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        user = resolve_user_by_email_or_username(ident)
        if not user or not bcrypt.check_password_hash(user.password_hash, password):
            flash("Invalid username, sign-in, or password.", "error")
            return render_template("login.html")
        remember = bool(request.form.get("remember"))
        login_user(user, remember=remember)
        next_url = request.form.get("next") or request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("leaderboard.home"))

    return render_template("login.html")


@bp.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
