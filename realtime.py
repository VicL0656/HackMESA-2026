from __future__ import annotations

from extensions import db, socketio
from models import FriendGroupMember, Match, User


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


def emit_dm_message(match_id: int, payload: dict) -> None:
    m = db.session.get(Match, match_id)
    if not m:
        return
    socketio.emit("dm_message", {**payload, "match_id": match_id}, room=f"user_{m.user_a_id}")
    socketio.emit("dm_message", {**payload, "match_id": match_id}, room=f"user_{m.user_b_id}")


def emit_group_message(group_id: int, payload: dict) -> None:
    rows = FriendGroupMember.query.filter_by(group_id=group_id).all()
    uids = {r.user_id for r in rows}
    for uid in uids:
        socketio.emit("group_message", {**payload, "group_id": group_id}, room=f"user_{uid}")
