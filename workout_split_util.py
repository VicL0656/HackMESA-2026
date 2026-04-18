"""Weekly workout split: JSON in User.workout_split (v1) or legacy free text."""

from __future__ import annotations

import json
from typing import Any

VERSION = 1
DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _empty_day() -> dict[str, Any]:
    return {"upper": False, "lower": False, "other": False, "other_text": ""}


def default_days() -> list[dict[str, Any]]:
    return [_empty_day() for _ in range(7)]


def _normalize_days(raw_list: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(7):
        d = raw_list[i] if i < len(raw_list) and isinstance(raw_list[i], dict) else {}
        out.append(
            {
                "upper": bool(d.get("upper")),
                "lower": bool(d.get("lower")),
                "other": bool(d.get("other")),
                "other_text": str(d.get("other_text") or "").strip()[:200],
            }
        )
    return out


def parse_structured(raw: str | None) -> list[dict[str, Any]] | None:
    """If raw is v1 JSON, return 7 day dicts; else None."""
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return None
    days = data.get("days")
    if not isinstance(days, list):
        return None
    return _normalize_days(days)


def form_context(raw: str | None) -> dict[str, Any]:
    """Template + form: days for Mon–Sun, optional legacy_plain if old text stored."""
    from split_presets import parse_v2

    if parse_v2(raw) is not None:
        return {"days": default_days(), "legacy_plain": None}
    parsed = parse_structured(raw)
    if parsed is not None:
        return {"days": parsed, "legacy_plain": None}
    text = (raw or "").strip()
    if text:
        return {"days": default_days(), "legacy_plain": text}
    return {"days": default_days(), "legacy_plain": None}


def card_lines(raw: str | None) -> tuple[list[str], str | None]:
    """(lines to show for structured week, legacy paragraph or None)."""
    from split_presets import parse_v2, summary_lines_v2

    if parse_v2(raw) is not None:
        return summary_lines_v2(raw), None
    ctx = form_context(raw)
    legacy = ctx["legacy_plain"]
    if legacy:
        return [], legacy
    lines: list[str] = []
    for i, d in enumerate(ctx["days"]):
        parts: list[str] = []
        if d["upper"]:
            parts.append("Upper")
        if d["lower"]:
            parts.append("Lower")
        if d["other"]:
            parts.append(d["other_text"] or "Other")
        if parts:
            lines.append(f"{DAY_LABELS[i]}: " + " · ".join(parts))
    return lines, None


def serialize_from_request(form: Any) -> str | None:
    """Build JSON from profile form checkboxes / other text fields."""
    days: list[dict[str, Any]] = []
    for d in range(7):
        upper = form.get(f"split_upper_{d}") == "1"
        lower = form.get(f"split_lower_{d}") == "1"
        other = form.get(f"split_other_{d}") == "1"
        text = (form.get(f"split_other_text_{d}") or "").strip()[:200]
        if not other:
            text = ""
        days.append(
            {
                "upper": upper,
                "lower": lower,
                "other": other,
                "other_text": text,
            }
        )
    if not any(x["upper"] or x["lower"] or x["other"] or x["other_text"] for x in days):
        return None
    return json.dumps({"version": VERSION, "days": days}, separators=(",", ":"))
