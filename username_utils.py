from __future__ import annotations

import re

# Letters (any case), digits, underscores; length 3–30. Uniqueness is case-insensitive (see find_user_by_username_ci).
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")


def normalize_username(raw: str | None) -> str | None:
    """Strip @, map invalid characters to underscores, preserve letter case."""
    if not raw:
        return None
    s = raw.strip().lstrip("@")
    s = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return None
    return s[:30]


def find_user_by_username_ci(handle: str | None):
    """Return the user row for this @handle, matching case-insensitively."""
    from sqlalchemy import func

    from models import User

    if not handle:
        return None
    h = handle.strip().lstrip("@")
    if not h:
        return None
    return User.query.filter(func.lower(User.username) == h.lower()).first()


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
    """Find a user by email, school_email, or @username (lazy-imports User to avoid cycles)."""
    from sqlalchemy import func

    from models import User

    s = (raw or "").strip()
    if not s:
        return None
    if s.startswith("@"):
        un = normalize_username(s)
        return find_user_by_username_ci(un) if un else None
    # Any address with @ is treated as email first (not only domains containing a dot).
    # Previously `user@localhost` or `student@campus` failed and fell through to a bogus username lookup.
    if "@" in s:
        el = s.lower()
        u = User.query.filter(func.lower(User.email) == el).first()
        if u:
            return u
        u = User.query.filter(User.school_email.isnot(None), func.lower(User.school_email) == el).first()
        if u:
            return u
        return None
    un = normalize_username(s)
    return find_user_by_username_ci(un) if un else None
