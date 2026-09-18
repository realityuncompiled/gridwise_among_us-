"""Deterministic validation for GridWise operator-note directives.

The language model is allowed to suggest an interpretation, but this module is
the gatekeeper.  Only its return value may be given to the optimizer.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


SUPPORTED_DIRECTIVE_TYPES = frozenset(
    {
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
    }
)


class DirectiveValidationError(ValueError):
    """Raised when an LLM interpretation is not safe to apply."""


def validate_directive_interpretations(
    raw_interpretations: Any,
    *,
    note_count: int,
    battery_capacity_kwh: float,
) -> list[dict[str, Any]]:
    """Return canonical, optimizer-safe directive entries.

    ``raw_interpretations`` may be the LLM's list directly or an object with a
    ``directives`` key.  This function intentionally rejects malformed output
    rather than guessing what the model meant.
    """
    _require_int(note_count, "note_count")
    if not 1 <= note_count <= 3:
        raise DirectiveValidationError("note_count must be between 1 and 3")

    capacity = _require_non_negative_finite(
        battery_capacity_kwh, "battery_capacity_kwh"
    )

    if isinstance(raw_interpretations, Mapping):
        raw_interpretations = raw_interpretations.get("directives")
    if not isinstance(raw_interpretations, Sequence) or isinstance(
        raw_interpretations, (str, bytes)
    ):
        raise DirectiveValidationError("LLM output must contain a directives array")
    if len(raw_interpretations) != note_count:
        raise DirectiveValidationError(
            "LLM output must contain exactly one directive for every operator note"
        )

    validated: list[dict[str, Any]] = []
    for expected_index, entry in enumerate(raw_interpretations):
        validated.append(
            _validate_entry(
                entry,
                expected_index=expected_index,
                battery_capacity_kwh=capacity,
            )
        )
    return validated


def _validate_entry(
    entry: Any, *, expected_index: int, battery_capacity_kwh: float
) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise DirectiveValidationError(
            f"directive_interpretation[{expected_index}] must be an object"
        )

    required = {
        "note_index",
        "applies",
        "directive_type",
        "structured_adjustment",
        "explanation",
    }
    if set(entry) != required:
        raise DirectiveValidationError(
            f"directive_interpretation[{expected_index}] must contain exactly "
            f"{sorted(required)}"
        )

    note_index = entry["note_index"]
    if not isinstance(note_index, int) or isinstance(note_index, bool):
        raise DirectiveValidationError("note_index must be an integer")
    if note_index != expected_index:
        raise DirectiveValidationError(
            "directive interpretations must be returned in note_index order "
            f"(expected {expected_index}, got {note_index})"
        )

    applies = entry["applies"]
    if not isinstance(applies, bool):
        raise DirectiveValidationError("applies must be a boolean")

    directive_type = entry["directive_type"]
    if directive_type not in SUPPORTED_DIRECTIVE_TYPES:
        raise DirectiveValidationError(f"unsupported directive_type: {directive_type!r}")

    explanation = entry["explanation"]
    if not isinstance(explanation, str) or not explanation.strip():
        raise DirectiveValidationError("explanation must be a non-empty string")

    adjustment = entry["structured_adjustment"]
    if directive_type == "no_op":
        if applies is not False or adjustment is not None:
            raise DirectiveValidationError(
                "no_op must use applies=false and structured_adjustment=null"
            )
        return {
            "note_index": note_index,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": explanation.strip(),
        }

    if applies is not True:
        raise DirectiveValidationError("applicable directives must use applies=true")
    if not isinstance(adjustment, Mapping):
        raise DirectiveValidationError(
            f"{directive_type} requires an object structured_adjustment"
        )

    canonical_adjustment = _validate_adjustment(
        directive_type,
        adjustment,
        battery_capacity_kwh=battery_capacity_kwh,
    )
    return {
        "note_index": note_index,
        "applies": True,
        "directive_type": directive_type,
        "structured_adjustment": canonical_adjustment,
        "explanation": explanation.strip(),
    }


def _validate_adjustment(
    directive_type: str,
    adjustment: Mapping[str, Any],
    *,
    battery_capacity_kwh: float,
) -> dict[str, Any]:
    required_keys = {
        "solar_reduction": {"hours", "factor"},
        "minimum_battery_reserve": {"hours", "minimum_energy_kwh"},
        "no_charge_window": {"hours"},
        "no_discharge_window": {"hours"},
        "max_grid_window": {"hours", "max_grid_kwh"},
    }[directive_type]

    if set(adjustment) != required_keys:
        raise DirectiveValidationError(
            f"{directive_type} structured_adjustment must contain exactly "
            f"{sorted(required_keys)}"
        )

    result: dict[str, Any] = {"hours": _validate_hours(adjustment["hours"])}
    if directive_type == "solar_reduction":
        factor = _require_non_negative_finite(adjustment["factor"], "factor")
        if factor > 1:
            raise DirectiveValidationError("solar_reduction factor must be between 0 and 1")
        result["factor"] = factor
    elif directive_type == "minimum_battery_reserve":
        reserve = _require_non_negative_finite(
            adjustment["minimum_energy_kwh"], "minimum_energy_kwh"
        )
        if reserve > battery_capacity_kwh:
            raise DirectiveValidationError(
                "minimum_energy_kwh cannot exceed battery capacity"
            )
        result["minimum_energy_kwh"] = reserve
    elif directive_type == "max_grid_window":
        result["max_grid_kwh"] = _require_non_negative_finite(
            adjustment["max_grid_kwh"], "max_grid_kwh"
        )
    return result


def _validate_hours(value: Any) -> list[int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DirectiveValidationError("hours must be an array")
    if not value:
        raise DirectiveValidationError("hours must not be empty")
    if any(not isinstance(hour, int) or isinstance(hour, bool) for hour in value):
        raise DirectiveValidationError("hours must contain only integers")
    hours = list(value)
    if any(hour < 0 or hour > 23 for hour in hours):
        raise DirectiveValidationError("hours must be integers from 0 through 23")
    if hours != sorted(hours) or len(hours) != len(set(hours)):
        raise DirectiveValidationError("hours must be unique and in ascending order")
    return hours


def _require_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DirectiveValidationError(f"{name} must be an integer")
    return value


def _require_non_negative_finite(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DirectiveValidationError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise DirectiveValidationError(f"{name} must be finite and non-negative")
    return number
