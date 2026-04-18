"""Workout split v2: JSON in User.workout_split with preset templates + per-day focus."""

from __future__ import annotations

import copy
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

# Preset -> allowed (value, label) for each weekday (radio groups in profile).
FOCUS_OPTIONS: dict[str, list[tuple[str, str]]] = {
    "upper_lower": [("upper", "Upper"), ("lower", "Lower"), ("rest", "Rest")],
    "ppl": [("push", "Push"), ("pull", "Pull"), ("legs", "Legs"), ("rest", "Rest")],
    "arnold": [("push", "Push"), ("pull", "Pull"), ("legs", "Legs"), ("rest", "Rest")],
    "bro_5day": [
        ("chest", "Chest"),
        ("back", "Back"),
        ("shoulders", "Shoulders"),
        ("legs", "Legs"),
        ("arms", "Arms"),
        ("rest", "Rest"),
    ],
    "full_body_3": [("full_body", "Full body"), ("rest", "Rest")],
}


def preset_display_name(key: str | None) -> str:
    if not key:
        return "Split template"
    return PRESET_LABELS.get(str(key).strip().lower(), str(key).replace("_", " ").title())


def focus_options_for_preset(preset: str | None) -> list[tuple[str, str]]:
    p = (preset or "ppl").strip().lower().replace("-", "_")
    return list(FOCUS_OPTIONS.get(p, FOCUS_OPTIONS["ppl"]))


def focus_label_for(preset: str, value: str) -> str:
    p = (preset or "ppl").strip().lower().replace("-", "_")
    for v, lbl in FOCUS_OPTIONS.get(p, FOCUS_OPTIONS["ppl"]):
        if v == value:
            return lbl
    return value.replace("_", " ").title()


def _day(rest: bool = False, exercises: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"rest": bool(rest), "exercises": exercises or []}


def _ex(name: str, sets: int = 3, reps: int = 8) -> dict[str, Any]:
    return {"name": name, "sets": sets, "reps": reps, "manual": False}


def default_day_focus(preset: str, days: list[Any]) -> list[str]:
    """Infer default day_focus (7 strings) from preset + template rest flags."""
    p = (preset or "").strip().lower().replace("-", "_")
    out: list[str] = ["rest"] * 7
    if not isinstance(days, list) or len(days) != 7:
        return out

    def is_rest(i: int) -> bool:
        d = days[i] if 0 <= i < len(days) else {}
        return isinstance(d, dict) and bool(d.get("rest"))

    if p == "upper_lower":
        train_i = 0
        for i in range(7):
            if is_rest(i):
                out[i] = "rest"
            else:
                out[i] = "upper" if train_i % 2 == 0 else "lower"
                train_i += 1
        return out

    if p in ("ppl", "arnold"):
        cyc = ("push", "pull", "legs")
        t = 0
        for i in range(7):
            if is_rest(i):
                out[i] = "rest"
            else:
                out[i] = cyc[t % 3]
                t += 1
        return out

    if p == "bro_5day":
        seq = ("chest", "back", "shoulders", "legs", "arms")
        bi = 0
        for i in range(7):
            if is_rest(i):
                out[i] = "rest"
            else:
                out[i] = seq[bi] if bi < len(seq) else "rest"
                bi += 1
        return out

    if p == "full_body_3":
        for i in range(7):
            out[i] = "rest" if is_rest(i) else "full_body"
        return out

    for i in range(7):
        out[i] = "rest" if is_rest(i) else "push"
    return out


def _allowed_values(preset: str) -> set[str]:
    return {v for v, _ in focus_options_for_preset(preset)}


def coerce_day_focus_list(preset: str, days: list[Any], posted: list[str] | None) -> list[str]:
    defaults = default_day_focus(preset, days)
    allowed = _allowed_values(preset)
    out: list[str] = []
    for i in range(7):
        raw = (posted[i] if posted and i < len(posted) else "") or ""
        v = str(raw).strip().lower()
        if v not in allowed:
            v = defaults[i] if defaults[i] in allowed else next(iter(allowed))
        out.append(v)
    return out


def ensure_day_focus(data: dict[str, Any]) -> list[str]:
    """Ensure data has valid day_focus; mutates data dict. Returns the 7-value list."""
    preset = str(data.get("preset") or "ppl").lower().replace("-", "_")
    days = data.get("days") or []
    if not isinstance(days, list) or len(days) != 7:
        data["day_focus"] = ["rest"] * 7
        return data["day_focus"]
    cur = data.get("day_focus")
    if isinstance(cur, list) and len(cur) == 7:
        allowed = _allowed_values(preset)
        fixed: list[str] = []
        defaults = default_day_focus(preset, days)
        for i in range(7):
            v = str(cur[i]).strip().lower() if cur[i] is not None else ""
            if v not in allowed:
                v = defaults[i]
            fixed.append(v)
        data["day_focus"] = fixed
        return fixed
    df = default_day_focus(preset, days)
    data["day_focus"] = df
    return df


def load_v2_split(raw: str | None) -> dict[str, Any] | None:
    """Full v2 JSON dict or None."""
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
    return data


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

    df = default_day_focus(p, days)
    return json.dumps({"version": VERSION, "preset": p, "days": days, "day_focus": df}, separators=(",", ":"))


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
    data = load_v2_split(raw)
    if not data:
        return []
    from workout_split_util import DAY_LABELS

    preset = str(data.get("preset") or "ppl")
    days = data.get("days") or []
    work = copy.deepcopy(data)
    focus = ensure_day_focus(work)
    lines: list[str] = []
    for i, d in enumerate(days):
        if not isinstance(d, dict):
            continue
        fl = focus_label_for(preset, focus[i])
        if focus[i] == "rest":
            lines.append(f"{DAY_LABELS[i]} ({fl})")
            continue
        exs = d.get("exercises") or []
        if d.get("rest") or not isinstance(exs, list) or not exs:
            lines.append(f"{DAY_LABELS[i]} ({fl}): —")
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
        lines.append(f"{DAY_LABELS[i]} ({fl}): " + (" · ".join(parts) if parts else "—"))
    return lines


def today_plan(raw: str | None, weekday_py: int) -> dict[str, Any] | None:
    """weekday_py: Monday=0 .. Sunday=6 (Python weekday() after (d+6)%7)."""
    data = load_v2_split(raw)
    if not data:
        return None
    wd = weekday_py % 7
    day = data["days"][wd]
    if not isinstance(day, dict):
        return None
    preset = str(data.get("preset") or "ppl")
    work = copy.deepcopy(data)
    focus = ensure_day_focus(work)
    fv = focus[wd]
    flabel = focus_label_for(preset, fv)
    if fv == "rest":
        return {"rest": True, "exercises": [], "focus": fv, "focus_label": flabel}
    if day.get("rest"):
        return {"rest": False, "exercises": [], "focus": fv, "focus_label": flabel}
    return {
        "rest": False,
        "exercises": day.get("exercises") or [],
        "focus": fv,
        "focus_label": flabel,
    }
