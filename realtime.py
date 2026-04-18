from __future__ import annotations

from extensions import db, socketio
from models import Match, User


def emit_leaderboard_refresh(user_id: int) -> None:
    user = db.session.get(User, user_id)
    if not user:
        return
    payload = {"reason": "workout_logged", "user_id": user_id}
    socketio.emit("leaderboard_update", payload, room=f"user_{user_id}")
    matches = Match.query.filter(
        (Match.user_a_id == user_id) | (Match.user_b_id == user_id)
    ).all()
    for m in matches:
        other = m.user_b_id if m.user_a_id == user_id else m.user_a_id
        socketio.emit("leaderboard_update", payload, room=f"user_{other}")
