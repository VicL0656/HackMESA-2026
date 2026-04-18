"""Workout split v2: JSON in User.workout_split — template days, day_focus, day_plans (custom + rest notes)."""

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
    "arnold": [
        ("chest_back", "Chest / Back"),
        ("shoulder_arms", "Shoulder / Arms"),
        ("legs", "Legs"),
        ("rest", "Rest"),
    ],
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

# Short copy for the “template ideas” list under the week planner.
EXERCISE_IDEAS_INTRO: dict[str, str] = {
    "upper_lower": "Template ideas for each weekday slot (upper vs lower vs rest in the preset).",
    "ppl": "Template ideas for each weekday slot (push / pull / legs pattern in the preset).",
    "arnold": "Template ideas for each weekday slot (chest-back, shoulder-arms, legs rotation in the preset).",
    "bro_5day": "Template ideas for each weekday slot (chest, back, shoulders, legs, arms in the preset).",
    "full_body_3": "Template ideas for each weekday slot (full-body sessions vs rest in the preset).",
    "custom": "Template ideas for each weekday slot.",
}


def exercise_ideas_intro(preset: str | None) -> str:
    p = (preset or "custom").strip().lower().replace("-", "_")
    return EXERCISE_IDEAS_INTRO.get(p, EXERCISE_IDEAS_INTRO["custom"])


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


def _empty_day_plan() -> dict[str, Any]:
    return {"custom": False, "rest_notes": "", "items": []}


def ensure_day_plans(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Ensure data['day_plans'] exists (7 entries). Mutates data. Returns list."""
    cur = data.get("day_plans")
    if isinstance(cur, list) and len(cur) == 7:
        fixed: list[dict[str, Any]] = []
        for i in range(7):
            e = cur[i] if isinstance(cur[i], dict) else {}
            items_in = e.get("items")
            items: list[dict[str, Any]] = []
            if isinstance(items_in, list):
                for it in items_in:
                    if not isinstance(it, dict):
                        continue
                    nm = str(it.get("name") or "").strip()[:120]
                    if not nm:
                        continue
                    items.append(
                        {
                            "name": nm,
                            "sets": it.get("sets"),
                            "reps": it.get("reps"),
                            "seconds": it.get("seconds"),
                            "note": str(it.get("note") or "").strip()[:500],
                        }
                    )
            fixed.append(
                {
                    "custom": bool(e.get("custom")),
                    "rest_notes": str(e.get("rest_notes") or "").strip()[:2000],
                    "items": items,
                }
            )
        data["day_plans"] = fixed
        return fixed
    dp = [_empty_day_plan() for _ in range(7)]
    data["day_plans"] = dp
    return dp


def _opt_int(raw: Any) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_day_plans_from_form(form: Any) -> list[dict[str, Any]]:
    """Read per-day custom plan + rest notes from POST (Flask request.form)."""
    out: list[dict[str, Any]] = []
    for d in range(7):
        custom = form.get(f"day_custom_{d}") == "1"
        rest_notes = (form.get(f"day_rest_notes_{d}") or "").strip()[:2000]
        items: list[dict[str, Any]] = []
        if custom:
            for i in range(32):
                name = (form.get(f"d{d}_ex_{i}_name") or "").strip()[:120]
                if not name:
                    continue
                items.append(
                    {
                        "name": name,
                        "sets": _opt_int(form.get(f"d{d}_ex_{i}_sets")),
                        "reps": _opt_int(form.get(f"d{d}_ex_{i}_reps")),
                        "seconds": _opt_int(form.get(f"d{d}_ex_{i}_seconds")),
                        "note": (form.get(f"d{d}_ex_{i}_note") or "").strip()[:500],
                    }
                )
        out.append({"custom": custom, "rest_notes": rest_notes, "items": items})
    return out


def _format_custom_plan_item(it: dict[str, Any]) -> str:
    nm = str(it.get("name") or "").strip()
    if not nm:
        return ""
    parts = [nm]
    sec = it.get("seconds")
    reps = it.get("reps")
    sets = it.get("sets")
    sr_parts: list[str] = []
    has_sets_reps = sets is not None and reps is not None and str(sets).strip() != "" and str(reps).strip() != ""
    if has_sets_reps:
        try:
            sr_parts.append(f"{int(sets)}×{int(reps)}")
        except (TypeError, ValueError):
            sr_parts.append(f"{sets}×{reps}")
    if sec is not None and str(sec).strip() != "":
        try:
            sr_parts.append(f"{int(sec)}s")
        except (TypeError, ValueError):
            sr_parts.append(f"{sec}s")
    if sr_parts:
        parts.append(" · ".join(sr_parts))
    note = str(it.get("note") or "").strip()
    if note:
        parts.append(f"({note})")
    return " ".join(parts) if len(parts) > 1 else nm


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

    if p == "arnold":
        cyc = ("chest_back", "shoulder_arms", "legs")
        t = 0
        for i in range(7):
            if is_rest(i):
                out[i] = "rest"
            else:
                out[i] = cyc[t % 3]
                t += 1
        return out

    if p == "ppl":
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
    dp = [_empty_day_plan() for _ in range(7)]
    return json.dumps(
        {"version": VERSION, "preset": p, "days": days, "day_focus": df, "day_plans": dp},
        separators=(",", ":"),
    )


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


def _template_exercise_parts(d: dict[str, Any]) -> list[str]:
    exs = d.get("exercises") or []
    if not isinstance(exs, list) or not exs:
        return []
    parts: list[str] = []
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
    return parts


def summary_lines_v2(raw: str | None) -> list[str]:
    data = load_v2_split(raw)
    if not data:
        return []
    from workout_split_util import DAY_LABELS

    preset = str(data.get("preset") or "ppl")
    days = data.get("days") or []
    work = copy.deepcopy(data)
    focus = ensure_day_focus(work)
    plans = ensure_day_plans(work)
    lines: list[str] = []
    for i, d in enumerate(days):
        if not isinstance(d, dict):
            continue
        fl = focus_label_for(preset, focus[i])
        plan = plans[i] if i < len(plans) else _empty_day_plan()
        if focus[i] == "rest":
            notes = (plan.get("rest_notes") or "").strip()
            if notes:
                lines.append(f"{DAY_LABELS[i]} ({fl}): {notes}")
            else:
                lines.append(f"{DAY_LABELS[i]} ({fl})")
            continue
        if plan.get("custom") and plan.get("items"):
            bits = [_format_custom_plan_item(x) for x in plan["items"]]
            bits = [b for b in bits if b]
            lines.append(f"{DAY_LABELS[i]} ({fl}): " + (" · ".join(bits) if bits else "—"))
            continue
        if d.get("rest"):
            lines.append(f"{DAY_LABELS[i]} ({fl}): —")
            continue
        parts = _template_exercise_parts(d)
        lines.append(f"{DAY_LABELS[i]} ({fl}): " + (" · ".join(parts) if parts else "—"))
    return lines


def _plan_item_to_exercise_dict(it: dict[str, Any]) -> dict[str, Any]:
    """Shape for log_workout template (exercises list)."""
    out: dict[str, Any] = {
        "name": str(it.get("name") or "").strip(),
        "sets": it.get("sets"),
        "reps": it.get("reps"),
        "seconds": it.get("seconds"),
        "note": str(it.get("note") or "").strip(),
    }
    return out


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
    plans = ensure_day_plans(work)
    plan = plans[wd] if wd < len(plans) else _empty_day_plan()
    fv = focus[wd]
    flabel = focus_label_for(preset, fv)
    if fv == "rest":
        return {
            "rest": True,
            "exercises": [],
            "focus": fv,
            "focus_label": flabel,
            "rest_notes": (plan.get("rest_notes") or "").strip(),
        }
    if plan.get("custom") and plan.get("items"):
        ex_out = [_plan_item_to_exercise_dict(x) for x in plan["items"] if str(x.get("name") or "").strip()]
        return {
            "rest": False,
            "exercises": ex_out,
            "focus": fv,
            "focus_label": flabel,
        }
    if day.get("rest"):
        return {"rest": False, "exercises": [], "focus": fv, "focus_label": flabel}
    return {
        "rest": False,
        "exercises": day.get("exercises") or [],
        "focus": fv,
        "focus_label": flabel,
    }
