"""Workout split v2: JSON in User.workout_split with preset templates."""

from __future__ import annotations

import json
from typing import Any

VERSION = 2
PRESET_KEYS = ("upper_lower", "ppl", "arnold", "bro_5day", "full_body_3")

PRESET_LABELS: dict[str, str] = {
    "upper_lower": "Upper / Lower",
    "ppl": "Push / Pull / Legs",
    "arnold": "Arnold split",
    "bro_5day": "Bro split (5 day)",
    "full_body_3": "Full body (3× / week)",
    "custom": "Custom template",
}


def preset_display_name(key: str | None) -> str:
    if not key:
        return "Split template"
    return PRESET_LABELS.get(str(key).strip().lower(), str(key).replace("_", " ").title())


def _day(rest: bool = False, exercises: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"rest": bool(rest), "exercises": exercises or []}


def _ex(name: str, sets: int = 3, reps: int = 8) -> dict[str, Any]:
    return {"name": name, "sets": sets, "reps": reps, "manual": False}


def build_preset(preset: str) -> str | None:
    """Return JSON string for preset, or None if unknown."""
    p = (preset or "").strip().lower().replace("-", "_")
    if p not in PRESET_KEYS:
        return None

    if p == "upper_lower":
        days = [
            _day(False, [_ex("Bench Press", 4, 6), _ex("Overhead Press", 3, 8), _ex("Barbell Row", 4, 8)]),
            _day(False, [_ex("Squat", 4, 6), _ex("Romanian Deadlift", 3, 8), _ex("Leg Press", 3, 12)]),
            _day(True),
            _day(False, [_ex("Incline Bench Press", 4, 8), _ex("Lat Pulldown", 4, 10), _ex("Cable Fly", 3, 12)]),
            _day(False, [_ex("Deadlift", 3, 5), _ex("Leg Curl", 3, 12), _ex("Calf Raise", 4, 15)]),
            _day(True),
            _day(False, [_ex("Full Body Circuit", 3, 10)]),
        ]
    elif p == "ppl":
        days = [
            _day(False, [_ex("Bench Press"), _ex("Incline Dumbbell Press"), _ex("Cable Fly"), _ex("Tricep Pushdown")]),
            _day(False, [_ex("Pull Ups"), _ex("Barbell Row"), _ex("Face Pull"), _ex("Barbell Curl")]),
            _day(False, [_ex("Squat"), _ex("Leg Press"), _ex("Leg Curl"), _ex("Standing Calf Raise")]),
            _day(False, [_ex("Overhead Press"), _ex("Lateral Raise"), _ex("Chest Dip"), _ex("Skullcrusher")]),
            _day(False, [_ex("Deadlift", 3, 5), _ex("Lat Pulldown"), _ex("Seated Row"), _ex("Hammer Curl")]),
            _day(False, [_ex("Front Squat"), _ex("Bulgarian Split Squat"), _ex("Leg Extension"), _ex("Seated Calf Raise")]),
            _day(True),
        ]
    elif p == "arnold":
        days = [
            _day(False, [_ex("Bench Press"), _ex("Dumbbell Fly"), _ex("Arnold Press"), _ex("Tricep Rope")]),
            _day(False, [_ex("Pull Ups"), _ex("T-Bar Row"), _ex("Barbell Curl"), _ex("Hammer Curl")]),
            _day(False, [_ex("Squat"), _ex("Leg Press"), _ex("Leg Curl"), _ex("Calf Raise")]),
            _day(False, [_ex("Incline Bench"), _ex("Lateral Raise"), _ex("Upright Row"), _ex("Overhead Extension")]),
            _day(False, [_ex("Deadlift", 3, 5), _ex("One Arm Row"), _ex("Preacher Curl"), _ex("Wrist Curl")]),
            _day(False, [_ex("Front Squat"), _ex("Lunge"), _ex("Leg Extension"), _ex("Seated Calf")]),
            _day(True),
        ]
    elif p == "bro_5day":
        days = [
            _day(False, [_ex("Chest — Bench Press"), _ex("Incline Press"), _ex("Flyes")]),
            _day(False, [_ex("Back — Deadlift", 3, 5), _ex("Lat Pulldown"), _ex("Cable Row")]),
            _day(False, [_ex("Shoulders — OHP"), _ex("Lateral Raise"), _ex("Rear Delt Fly")]),
            _day(False, [_ex("Legs — Squat"), _ex("Leg Press"), _ex("Leg Curl"), _ex("Calves")]),
            _day(False, [_ex("Arms — Curl"), _ex("Hammer Curl"), _ex("Tricep Pushdown"), _ex("Rope Extension")]),
            _day(True),
            _day(True),
        ]
    else:  # full_body_3
        block = [_ex("Squat"), _ex("Bench Press"), _ex("Barbell Row"), _ex("Plank", 3, 60)]
        days = [
            _day(False, block),
            _day(True),
            _day(False, block),
            _day(True),
            _day(False, block),
            _day(True),
            _day(True),
        ]

    return json.dumps({"version": VERSION, "preset": p, "days": days}, separators=(",", ":"))


def parse_v2(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return None
    days = data.get("days")
    if not isinstance(days, list) or len(days) != 7:
        return None
    return {"preset": str(data.get("preset") or "custom"), "days": days}


def summary_lines_v2(raw: str | None) -> list[str]:
    parsed = parse_v2(raw)
    if not parsed:
        return []
    from workout_split_util import DAY_LABELS

    lines: list[str] = []
    for i, d in enumerate(parsed["days"]):
        if not isinstance(d, dict):
            continue
        if d.get("rest"):
            lines.append(f"{DAY_LABELS[i]}: Rest")
            continue
        exs = d.get("exercises") or []
        if not isinstance(exs, list) or not exs:
            lines.append(f"{DAY_LABELS[i]}: —")
            continue
        parts = []
        for e in exs:
            if not isinstance(e, dict):
                continue
            nm = str(e.get("name") or "").strip()
            if not nm:
                continue
            s = e.get("sets")
            r = e.get("reps")
            if s and r:
                parts.append(f"{nm} ({s}×{r})")
            else:
                parts.append(nm)
        lines.append(f"{DAY_LABELS[i]}: " + (" · ".join(parts) if parts else "—"))
    return lines


def today_plan(raw: str | None, weekday_py: int) -> dict[str, Any] | None:
    """weekday_py: Monday=0 .. Sunday=6 (Python weekday() after (d+6)%7)."""
    parsed = parse_v2(raw)
    if not parsed:
        return None
    d = weekday_py % 7
    day = parsed["days"][d]
    if not isinstance(day, dict):
        return None
    return {"rest": bool(day.get("rest")), "exercises": day.get("exercises") or []}
