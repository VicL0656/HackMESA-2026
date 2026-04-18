"""One-time backfill: ensure Tom exists and every *real* user has a gym-friend match with Tom.

Skips seed accounts (emails ending in @gymlink.demo, matching seed.py) and skips Tom.

Run on Railway or locally with DATABASE_URL set:

  python scripts/backfill_tom_for_real_users.py

Safe to run multiple times: befriend_tom is idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from models import Match, User  # noqa: E402
from tom_friend import befriend_tom, ensure_tom_user, get_tom_user, is_tom_user  # noqa: E402


def _is_seed_demo_account(user: User) -> bool:
    return (user.email or "").strip().lower().endswith("@gymlink.demo")


def _tom_pair_ids(user_id: int, tom_id: int) -> tuple[int, int]:
    return (user_id, tom_id) if user_id < tom_id else (tom_id, user_id)


def main() -> None:
    with app.app_context():
        ensure_tom_user()
        db.session.flush()
        tom = get_tom_user()
        if not tom:
            print("ERROR: Tom user could not be created or found.")
            return

        candidates: list[User] = []
        for u in User.query.order_by(User.id).all():
            if is_tom_user(u):
                continue
            if _is_seed_demo_account(u):
                continue
            candidates.append(u)

        added = 0
        already = 0
        for u in candidates:
            lo, hi = _tom_pair_ids(u.id, tom.id)
            had = Match.query.filter_by(user_a_id=lo, user_b_id=hi).first() is not None
            befriend_tom(u.id)
            if had:
                already += 1
            else:
                now_has = Match.query.filter_by(user_a_id=lo, user_b_id=hi).first() is not None
                if now_has:
                    added += 1

        db.session.commit()
        print(f"Tom user id={tom.id} @{tom.username}")
        print(f"Real users considered: {len(candidates)}")
        print(f"New Tom friendships created: {added}")
        print(f"Already linked to Tom: {already}")


if __name__ == "__main__":
    main()
