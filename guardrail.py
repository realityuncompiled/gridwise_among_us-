"""
guardrail.py
------------
LLM-er raw JSON output ke validate kore safe, deterministic form-e convert kore.

Kaj kore ki:
1) JSON parse kore — fail hoile default (no-op) interpretation dey, crash kore na
2) Chacks ki "interpretations" list ase, each item a # of expected fields ase
3) directive_type jodi unknown hoy tahole setake "no_op" kore dey (reject kore na — interpret kore "ignore")
4) structured_adjustment ke per-type expected shape e validate kore (missing keys, type-vhul, out-of-range)
5) hour indices 0..23-r moddhe, factors 0..1, etc. — clamp kore safe range-e ane
6) applies=False items eke "no_op" kore dey, sathe explanation preserve kore

Ekhane kono LLM call nei — purely deterministic validation layer.
"""

from __future__ import annotations

from typing import List, Dict, Any


ALLOWED_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


def _safe_int(x: Any, lo: int, hi: int, default: int) -> int:
    """x ke integer-e convert kore [lo, hi] range-e clamp kore."""
    try:
        v = int(x)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _safe_float(x: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _clamp_hour(v: Any, default: int = 0) -> int:
    return _safe_int(v, 0, 23, default)


def _normalize_one(raw: Any) -> Dict:
    """Ekta raw interpretation dict ke safe, normalized form-e convert kore."""
    if not isinstance(raw, dict):
        return {
            "note_index": -1,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "guardrail: raw item was not a dict",
        }

    # note_index
    note_index = _safe_int(raw.get("note_index"), 0, 100, -1)

    # applies (strict bool)
    applies = bool(raw.get("applies", False))

    # directive_type — unknown type thakle "no_op" kore dey
    dtype = raw.get("directive_type", "no_op")
    if dtype not in ALLOWED_TYPES:
        explanation = raw.get("explanation", "")
        return {
            "note_index": note_index,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": f"guardrail: unknown directive_type '{dtype}' ignored. {explanation}".strip(),
        }

    # applies=False hole — short-circuit, no_op hisebe return
    if not applies:
        return {
            "note_index": note_index,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": str(raw.get("explanation", "")) or "Note does not apply to the schedule.",
        }

    sa = raw.get("structured_adjustment")
    explanation = str(raw.get("explanation", "")) or f"{dtype} applied per operator note."

    # each type-r jonne expected shape validate kore
    if dtype == "solar_reduction":
        if not isinstance(sa, dict):
            return _reject(note_index, dtype, "structured_adjustment missing/invalid")
        adj = {
            "start_hour": _clamp_hour(sa.get("start_hour")),
            "end_hour":   _clamp_hour(sa.get("end_hour")),
            "factor":     _safe_float(sa.get("factor"), 0.0, 1.0, 0.5),
        }
        if adj["end_hour"] < adj["start_hour"]:
            adj["start_hour"], adj["end_hour"] = adj["end_hour"], adj["start_hour"]
        return {"note_index": note_index, "applies": True, "directive_type": dtype,
                "structured_adjustment": adj, "explanation": explanation}

    if dtype == "minimum_battery_reserve":
        if not isinstance(sa, dict):
            return _reject(note_index, dtype, "structured_adjustment missing/invalid")
        adj = {"value_kwh": _safe_float(sa.get("value_kwh"), 0.0, 1e6, 0.0)}
        return {"note_index": note_index, "applies": True, "directive_type": dtype,
                "structured_adjustment": adj, "explanation": explanation}

    if dtype in ("no_charge_window", "no_discharge_window"):
        if not isinstance(sa, dict):
            return _reject(note_index, dtype, "structured_adjustment missing/invalid")
        adj = {
            "start_hour": _clamp_hour(sa.get("start_hour")),
            "end_hour":   _clamp_hour(sa.get("end_hour")),
        }
        if adj["end_hour"] < adj["start_hour"]:
            adj["start_hour"], adj["end_hour"] = adj["end_hour"], adj["start_hour"]
        return {"note_index": note_index, "applies": True, "directive_type": dtype,
                "structured_adjustment": adj, "explanation": explanation}

    if dtype == "max_grid_window":
        if not isinstance(sa, dict):
            return _reject(note_index, dtype, "structured_adjustment missing/invalid")
        adj = {
            "start_hour":         _clamp_hour(sa.get("start_hour")),
            "end_hour":           _clamp_hour(sa.get("end_hour")),
            "max_kwh_per_hour":   _safe_float(sa.get("max_kwh_per_hour"), 0.0, 1e6, 100.0),
        }
        if adj["end_hour"] < adj["start_hour"]:
            adj["start_hour"], adj["end_hour"] = adj["end_hour"], adj["start_hour"]
        return {"note_index": note_index, "applies": True, "directive_type": dtype,
                "structured_adjustment": adj, "explanation": explanation}

    # no_op
    return {"note_index": note_index, "applies": False, "directive_type": "no_op",
            "structured_adjustment": None, "explanation": explanation}


def _reject(note_index: int, dtype: str, msg: str) -> Dict:
    return {
        "note_index": note_index,
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": f"guardrail: {msg} (original: {dtype})",
    }


def validate_interpretations(raw: Any, expected_count: int) -> List[Dict]:
    """Top-level raw response (LLM theke ase) ke list of safe interpretations-e convert kore."""
    # Case: raw is not even a list
    if not isinstance(raw, dict):
        # wrap empty list path
        items = []
    else:
        items = raw.get("interpretations", [])

    if not isinstance(items, list):
        items = []

    # Pad up to expected_count with no_op placeholders
    out: List[Dict] = []
    for i in range(expected_count):
        if i < len(items):
            norm = _normalize_one(items[i])
            # note_index fix: should match position
            if norm["note_index"] in (-1, None):
                norm["note_index"] = i
            out.append(norm)
        else:
            out.append({
                "note_index": i,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "guardrail: LLM did not return a matching entry; treated as no-op.",
            })
    # Extra items from LLM? drop them.
    return out


def _selftest() -> None:
    # Case 1: clean valid
    raw = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"start_hour": 13, "end_hour": 15, "factor": 0.3},
                "explanation": "দুপুরে সোলার কমবে",
            },
            {
                "note_index": 1,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "ক্যাফেটেরিয়ার মেনু",
            },
        ]
    }
    out = validate_interpretations(raw, expected_count=2)
    print("case1:", out)
    assert out[0]["directive_type"] == "solar_reduction"
    assert out[1]["directive_type"] == "no_op"

    # Case 2: malformed — missing fields, bad types, out-of-range
    raw = {
        "interpretations": [
            {"note_index": 0, "applies": True, "directive_type": "solar_reduction",
             "structured_adjustment": {"start_hour": "13", "end_hour": 99, "factor": 1.9}},
            {"directive_type": "max_quantum_grid", "applies": True},
            {"note_index": 99, "directive_type": "no_op", "applies": True,
             "structured_adjustment": None},
        ]
    }
    out = validate_interpretations(raw, expected_count=4)
    print("case2:", out)
    # case2[0] should clamp factor and hours
    assert out[0]["structured_adjustment"]["end_hour"] == 23
    assert out[0]["structured_adjustment"]["factor"] == 1.0
    # case2[1] unknown directive -> no_op
    assert out[1]["directive_type"] == "no_op"
    # case2[2] applies=True but no_op -> still no_op
    assert out[2]["directive_type"] == "no_op"
    # padded
    assert out[3]["directive_type"] == "no_op"

    # Case 3: complete garbage
    out = validate_interpretations("not a dict at all", expected_count=1)
    print("case3:", out)
    assert out[0]["directive_type"] == "no_op"

    print("guardrail selftest OK")


if __name__ == "__main__":
    _selftest()
