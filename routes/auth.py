from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from extensions import bcrypt, db
from mail_util import mail_configured, send_email
from models import PasswordResetToken, Streak, User
from models import utcnow
from tom_friend import TOM_EMAIL, befriend_tom, ensure_tom_user, is_reserved_username
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

        if is_reserved_username(username):
            flash("That username is reserved.", "error")
            return render_template("register.html")

        if email.strip().lower() == TOM_EMAIL.lower():
            flash("That sign-in address is reserved.", "error")
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
        ensure_tom_user()
        befriend_tom(user.id)
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
        ensure_tom_user()
        befriend_tom(user.id)
        db.session.commit()
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


def _hash_reset_token(token: str) -> str:
    secret = (current_app.config.get("SECRET_KEY") or "").encode()
    return hashlib.sha256(secret + b"|" + token.encode("utf-8")).hexdigest()


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("leaderboard.home"))
    if request.method == "POST":
        from username_utils import resolve_user_by_email_or_username

        raw = (request.form.get("identifier") or request.form.get("email") or "").strip()
        user = resolve_user_by_email_or_username(raw)
        if not user:
            flash("If that email is on file, you will receive reset instructions shortly.", "info")
            return redirect(url_for("auth.login"))
        raw = secrets.token_urlsafe(32)
        th = _hash_reset_token(raw)
        PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).delete(
            synchronize_session=False
        )
        db.session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=th,
                expires_at=utcnow() + timedelta(hours=2),
            )
        )
        db.session.commit()
        link = url_for("auth.reset_password", token=raw, _external=True)
        body = (
            "You asked to reset your GymLink password.\n\n"
            f"Open this link within 2 hours (one-time use):\n{link}\n\n"
            "If you did not request this, you can ignore this email."
        )
        if mail_configured() and send_email(user.email, "GymLink password reset", body):
            flash("Check your email for a reset link.", "success")
        else:
            flash(
                "Password email is not configured on this server. Contact the host or set MAIL_* env vars. "
                f"Dev link (do not share): {link}",
                "info",
            )
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("leaderboard.home"))
    th = _hash_reset_token(token)
    row = (
        PasswordResetToken.query.filter_by(token_hash=th, used_at=None)
        .order_by(PasswordResetToken.id.desc())
        .first()
    )
    if not row or row.expires_at < utcnow():
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        pw = request.form.get("password") or ""
        pw2 = request.form.get("password_confirm") or ""
        if len(pw) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("reset_password.html", token=token)
        if pw != pw2:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)
        user = db.session.get(User, row.user_id)
        if not user:
            flash("Account not found.", "error")
            return redirect(url_for("auth.login"))
        h = bcrypt.generate_password_hash(pw)
        if isinstance(h, bytes):
            h = h.decode("utf-8")
        user.password_hash = h
        row.used_at = utcnow()
        db.session.commit()
        flash("Password updated. You can log in now.", "success")
        return redirect(url_for("auth.login"))
    return render_template("reset_password.html", token=token)
