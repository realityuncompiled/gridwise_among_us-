"""
Deterministic Guardrails module for Smart Campus Energy Optimization Challenge.
Strictly validates and sanitizes LLM-generated directives according to Problem Statement Section 08.
"""

from typing import Any, Dict, List, Optional
from schemas import DirectiveInterpretationEntry, BatteryConfig, DirectiveType

VALID_DIRECTIVE_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op"
}


def sanitize_hours(raw_hours: Any) -> List[int]:
    """
    Validates and converts raw hours to unique integers in [0, 23] sorted in ascending order.
    Raises ValueError if hours are invalid or outside 0..23.
    """
    if not isinstance(raw_hours, list):
        raise ValueError(f"hours must be a list, got {type(raw_hours)}")
    if len(raw_hours) == 0:
        raise ValueError("hours array cannot be empty for an active directive")
    
    clean_hours = set()
    for h in raw_hours:
        if not isinstance(h, int) or isinstance(h, bool):
            try:
                # If float that is an integer e.g. 13.0
                h_float = float(h)
                if not h_float.is_integer():
                    raise ValueError()
                h = int(h_float)
            except Exception:
                raise ValueError(f"Invalid hour value: {h}")
        if h < 0 or h > 23:
            raise ValueError(f"Hour {h} outside valid range [0, 23]")
        clean_hours.add(h)
        
    return sorted(list(clean_hours))


def validate_directive_entry(
    entry: Dict[str, Any],
    note_idx: int,
    battery: BatteryConfig
) -> DirectiveInterpretationEntry:
    """
    Validates a single directive entry against Section 08 guardrails.
    Returns a clean DirectiveInterpretationEntry or a safe no_op fallback.
    """
    try:
        raw_type = entry.get("directive_type")
        if raw_type not in VALID_DIRECTIVE_TYPES:
            raise ValueError(f"Unsupported directive type: {raw_type}")

        raw_applies = entry.get("applies", False)
        raw_adj = entry.get("structured_adjustment")
        explanation = entry.get("explanation", "").strip() or "Operator note processed."

        if raw_type == "no_op":
            return DirectiveInterpretationEntry(
                note_index=note_idx,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation=explanation
            )

        # For all other directives, applies must be True and structured_adjustment must not be None
        if not isinstance(raw_adj, dict):
            raise ValueError(f"Missing structured_adjustment for directive {raw_type}")

        # Validate hours array
        clean_hours = sanitize_hours(raw_adj.get("hours"))

        if raw_type == "solar_reduction":
            factor = raw_adj.get("factor")
            if factor is None or not isinstance(factor, (int, float)):
                raise ValueError(f"solar_reduction requires numeric factor, got {factor}")
            factor = float(factor)
            if factor < 0.0 or factor > 1.0:
                raise ValueError(f"solar_reduction factor must be in [0.0, 1.0], got {factor}")
            
            clean_adj = {
                "hours": clean_hours,
                "factor": round(factor, 4)
            }

        elif raw_type == "minimum_battery_reserve":
            reserve = raw_adj.get("minimum_energy_kwh")
            if reserve is None or not isinstance(reserve, (int, float)):
                raise ValueError(f"minimum_battery_reserve requires numeric minimum_energy_kwh, got {reserve}")
            reserve = float(reserve)
            if reserve < 0.0 or reserve > battery.capacity_kwh:
                raise ValueError(f"minimum_energy_kwh ({reserve}) must be between 0 and battery capacity ({battery.capacity_kwh})")
            
            clean_adj = {
                "hours": clean_hours,
                "minimum_energy_kwh": round(reserve, 4)
            }

        elif raw_type in ("no_charge_window", "no_discharge_window"):
            clean_adj = {
                "hours": clean_hours
            }

        elif raw_type == "max_grid_window":
            max_grid = raw_adj.get("max_grid_kwh")
            if max_grid is None or not isinstance(max_grid, (int, float)):
                raise ValueError(f"max_grid_window requires numeric max_grid_kwh, got {max_grid}")
            max_grid = float(max_grid)
            if max_grid < 0.0:
                raise ValueError(f"max_grid_kwh ({max_grid}) must be non-negative")
            
            clean_adj = {
                "hours": clean_hours,
                "max_grid_kwh": round(max_grid, 4)
            }

        else:
            raise ValueError(f"Unhandled directive type: {raw_type}")

        return DirectiveInterpretationEntry(
            note_index=note_idx,
            applies=True,
            directive_type=raw_type,
            structured_adjustment=clean_adj,
            explanation=explanation
        )

    except Exception as e:
        # SAFE FAILURE: If LLM returns malformed or unsupported output, fallback gracefully to no_op
        # rather than crashing or hallucinating an unsupported directive.
        return DirectiveInterpretationEntry(
            note_index=note_idx,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation=f"Fallback to no_op due to validation constraint: {str(e)}"
        )


def validate_and_guard_directives(
    raw_directives: List[Dict[str, Any]],
    operator_notes: List[str],
    battery: BatteryConfig
) -> List[DirectiveInterpretationEntry]:
    """
    Validates the entire list of candidate directives:
    - Guarantees exactly one entry per operator note in note_index order 0..N-1.
    - Applies strict schema and bounds guardrails.
    """
    num_notes = len(operator_notes)
    
    # Map by note_index
    indexed_entries: Dict[int, Dict[str, Any]] = {}
    for entry in raw_directives:
        if isinstance(entry, dict):
            idx = entry.get("note_index")
            if isinstance(idx, int) and 0 <= idx < num_notes and idx not in indexed_entries:
                indexed_entries[idx] = entry

    # If raw list was just an array matching notes in order
    if len(indexed_entries) < num_notes:
        for i, item in enumerate(raw_directives):
            if i < num_notes and i not in indexed_entries and isinstance(item, dict):
                indexed_entries[i] = item

    clean_results: List[DirectiveInterpretationEntry] = []
    for idx in range(num_notes):
        entry_data = indexed_entries.get(idx, {
            "note_index": idx,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "No valid directive extracted; defaulted to no_op."
        })
        validated_entry = validate_directive_entry(entry_data, idx, battery)
        clean_results.append(validated_entry)

    return clean_results
