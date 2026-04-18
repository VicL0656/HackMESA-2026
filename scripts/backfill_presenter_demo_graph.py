"""Repair presenter (jordan_blake) demo friend graph without wiping the DB.

Older seeds only paired (Jordan, Mia) plus Tom. This script ensures:
- Tom exists and presenter is befriended with Tom
- Presenter has a Match with every other @gymlink.demo user (seed roster)

Does not delete workouts or other users' data.

  python scripts/backfill_presenter_demo_graph.py
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
from username_utils import find_user_by_username_ci  # noqa: E402
from models import utcnow  # noqa: E402
from tom_friend import befriend_tom, ensure_tom_user, get_tom_user, is_tom_user  # noqa: E402

PRESENTER_USERNAME = "jordan_blake"


def _ordered(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def main() -> None:
    with app.app_context():
        ensure_tom_user()
        db.session.flush()
        presenter = find_user_by_username_ci(PRESENTER_USERNAME)
        if not presenter:
            print(f"No user @{PRESENTER_USERNAME}; skip.")
            return

        befriend_tom(presenter.id)

        added = 0
        when = utcnow()
        for u in User.query.order_by(User.id).all():
            if u.id == presenter.id or is_tom_user(u):
                continue
            if not (u.email or "").strip().lower().endswith("@gymlink.demo"):
                continue
            lo, hi = _ordered(presenter.id, u.id)
            if Match.query.filter_by(user_a_id=lo, user_b_id=hi).first():
                continue
            db.session.add(Match(user_a_id=lo, user_b_id=hi, matched_at=when))
            added += 1

        db.session.commit()
        tom = get_tom_user()
        print(f"Presenter @{presenter.username} id={presenter.id}")
        print(f"New presenter-to-seed matches created: {added}")
        if tom:
            print(f"Tom id={tom.id} (@{tom.username}); befriend_tom applied.")


if __name__ == "__main__":
    main()
