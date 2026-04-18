"""Hash / verify personal tokens for Apple Shortcuts → GymLink HTTP bridge."""

from __future__ import annotations

import hashlib


def hash_health_bridge_token(secret: str, token: str) -> str:
    s = (secret or "").encode("utf-8")
    return hashlib.sha256(s + b"|gymlink.health_bridge|" + token.encode("utf-8")).hexdigest()
