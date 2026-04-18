"""Search U.S. postsecondary institutions from IPEDS-derived JSON (see scripts/build_us_institutions.py)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_JSON = Path(__file__).resolve().parent / "static" / "data" / "us_institutions.json"
_cache: dict[str, Any] | None = None


def _data_path() -> Path:
    override = (os.environ.get("GYMLINK_INSTITUTIONS_JSON") or "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_JSON


def _load() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = _data_path()
    if not path.is_file():
        _cache = {"meta": {}, "institutions": []}
        return _cache
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _cache = {"meta": {}, "institutions": []}
        return _cache
    if "institutions" not in raw:
        raw = {"meta": raw.get("meta", {}), "institutions": []}
    _cache = raw
    return _cache


def institution_count() -> int:
    return len(_load().get("institutions", []))


def search_institutions(query: str, limit: int = 25) -> list[dict[str, str]]:
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []
    lim = max(1, min(int(limit), 50))
    insts: list[dict[str, str]] = _load().get("institutions", [])

    scored: list[tuple[tuple[int, str], dict[str, str]]] = []
    for row in insts:
        name = row.get("name", "")
        nl = name.lower()
        city = (row.get("city") or "").lower()
        state = (row.get("state") or "").lower()
        key: tuple[int, str]
        if nl.startswith(q):
            key = (0, nl)
        elif q in nl:
            key = (1, nl)
        elif city.startswith(q):
            key = (2, nl)
        elif q in city or q in state:
            key = (3, nl)
        else:
            continue
        scored.append((key, row))

    scored.sort(key=lambda x: (x[0][0], x[0][1]))
    out: list[dict[str, str]] = []
    for _, row in scored[:lim]:
        city = (row.get("city") or "").strip()
        state = (row.get("state") or "").strip()
        if city and state:
            loc = f"{city}, {state}"
        else:
            loc = city or state
        tier = (row.get("control") or "").strip()
        lvl = (row.get("level") or "").strip()
        bits = [b for b in (tier, lvl) if b]
        subtitle = " · ".join([loc] + bits) if loc else " · ".join(bits)
        out.append(
            {
                "name": row["name"],
                "subtitle": subtitle,
                "unitid": row.get("unitid", ""),
            }
        )
    return out
