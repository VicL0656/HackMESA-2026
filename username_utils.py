from __future__ import annotations

import re

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")


def normalize_username(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().lower().lstrip("@")
    s = re.sub(r"[^a-z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return None
    return s[:30]


def assign_username_if_missing(user) -> str:
    """Set a unique username when the DB row is NULL/empty (legacy SQLite)."""
    if (getattr(user, "username", None) or "").strip():
        return user.username.strip()

    import re

    from extensions import db
    from models import User

    email = user.email or f"id{user.id}@local"
    base = email.split("@")[0].lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    if len(base) < 3:
        base = f"user{user.id}"
    base = base[:24]
    cand = base
    suffix = 0
    while True:
        clash = User.query.filter(User.username == cand, User.id != user.id).first()
        if not clash:
            break
        suffix += 1
        cand = f"{base}_{suffix}"[:30]
    user.username = cand
    db.session.commit()
    return cand


def resolve_user_by_email_or_username(raw: str):
    """Find a user by email or @username (lazy-imports User to avoid cycles)."""
    from models import User

    s = (raw or "").strip()
    if not s:
        return None
    if s.startswith("@"):
        un = normalize_username(s)
        return User.query.filter_by(username=un).first() if un else None
    if "@" in s:
        left, right = s.split("@", 1)
        if left and "." in right:
            return User.query.filter_by(email=s.lower()).first()
    un = normalize_username(s)
    return User.query.filter_by(username=un).first() if un else None
