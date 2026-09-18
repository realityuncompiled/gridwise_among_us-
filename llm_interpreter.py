import json
import os
from typing import List, Dict, Any
from google import genai
from google.genai import types

# ------------------------------------------------------------------
# 1. CONSTANTS & GUARDRAIL SETUP
# ------------------------------------------------------------------

SUPPORTED_DIRECTIVES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op"
}

SYSTEM_PROMPT = """You are an expert energy management directive interpreter for a smart campus optimization system.
Your job is to read operator notes and extract structured directives for a 24-hour energy schedule (hours 0 through 23).

RULES FOR INTERPRETATION:
1. Output MUST strictly be a JSON array containing exactly one interpretation object per input note, in the exact order of note_index (0, 1, ... N-1).
2. Allowed directive types are strictly:
   - solar_reduction -> structured_adjustment: {"hours": [int], "factor": float} (Note: factor is the REMAINING solar fraction. E.g., 80% drop means factor = 0.2)
   - minimum_battery_reserve -> structured_adjustment: {"hours": [int], "minimum_energy_kwh": float}
   - no_charge_window -> structured_adjustment: {"hours": [int]}
   - no_discharge_window -> structured_adjustment: {"hours": [int]}
   - max_grid_window -> structured_adjustment: {"hours": [int], "max_grid_kwh": float}
   - no_op -> structured_adjustment: null
3. Time Windows: Whole-hour intervals. Start hour included, end hour excluded. (e.g., "1 PM to 3 PM" means hours [13, 14]).
4. If a note is irrelevant to today's 24-hour energy schedule, set applies=false, directive_type="no_op", and structured_adjustment=null.
5. For all non-no_op directives, set applies=true.
"""

# ------------------------------------------------------------------
# 2. GUARDRAIL VALIDATOR
# ------------------------------------------------------------------

def validate_and_clean_directive(
    entry: Dict[str, Any], 
    expected_index: int, 
    battery_capacity: float
) -> Dict[str, Any]:
    """
    Validates raw LLM output against strict problem statement guardrails (Section 08).
    Applies safe fallback for malformed output.
    """
    # Guardrail: Index alignment
    entry["note_index"] = expected_index

    directive_type = entry.get("directive_type")

    # Guardrail: Allowed directive types check
    if directive_type not in SUPPORTED_DIRECTIVES:
        return {
            "note_index": expected_index,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Safe Failure: Unsupported directive type from LLM."
        }

    # Guardrail: no_op semantics (applies = false, adjustment = null)
    if directive_type == "no_op":
        return {
            "note_index": expected_index,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": entry.get("explanation", "Note does not affect energy schedule.")
        }

    # Non-no_op directives must have applies = True
    entry["applies"] = True
    adj = entry.get("structured_adjustment") or {}

    # Guardrail: Hours array validation (unique integers 0-23 in ascending order)
    raw_hours = adj.get("hours", [])
    if not isinstance(raw_hours, list):
        raw_hours = []
    
    clean_hours = sorted(list(set(
        [h for h in raw_hours if isinstance(h, int) and 0 <= h <= 23]
    )))
    adj["hours"] = clean_hours

    # Guardrail: Numeric limits per directive type
    if directive_type == "solar_reduction":
        try:
            factor = float(adj.get("factor", 1.0))
            adj["factor"] = max(0.0, min(1.0, factor))  # 0.0 <= factor <= 1.0
        except (ValueError, TypeError):
            adj["factor"] = 1.0

    elif directive_type == "minimum_battery_reserve":
        try:
            reserve = float(adj.get("minimum_energy_kwh", 0.0))
            adj["minimum_energy_kwh"] = max(0.0, min(battery_capacity, reserve))
        except (ValueError, TypeError):
            adj["minimum_energy_kwh"] = 0.0

    elif directive_type == "max_grid_window":
        try:
            max_grid = float(adj.get("max_grid_kwh", 0.0))
            adj["max_grid_kwh"] = max(0.0, max_grid)
        except (ValueError, TypeError):
            adj["max_grid_kwh"] = 0.0

    entry["structured_adjustment"] = adj
    return entry


def apply_guardrails(
    raw_interpretations: List[Dict[str, Any]], 
    num_notes: int, 
    battery_capacity: float
) -> List[Dict[str, Any]]:
    """
    Enforces exact note count, index ordering, and guardrails for all directives.
    """
    cleaned_list = []
    
    for i in range(num_notes):
        # Match entry by index or create fallback if missing
        raw_entry = next((item for item in raw_interpretations if item.get("note_index") == i), None)
        
        if not raw_entry:
            raw_entry = {
                "note_index": i,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "Fallback: Missing interpretation mapping for this note."
            }

        cleaned_entry = validate_and_clean_directive(raw_entry, i, battery_capacity)
        cleaned_list.append(cleaned_entry)

    return cleaned_list

# ------------------------------------------------------------------
# 3. LLM INTERPRETER PIPELINE
# ------------------------------------------------------------------

def interpret_operator_notes(
    operator_notes: List[str], 
    battery_capacity: float
) -> List[Dict[str, Any]]:
    """
    Calls Gemini LLM to interpret natural language notes and returns guardrail-validated directives.
    """
    if not operator_notes:
        return []

    # Format user prompt
    user_prompt = f"Interpret the following operator notes:\n{json.dumps(operator_notes, indent=2)}"

    try:
        # Initialize Gemini Client (Uses GEMINI_API_KEY environment variable)
        client = genai.Client()
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.1
            ),
        )

        raw_json_str = response.text
        raw_interpretations = json.loads(raw_json_str)

        if not isinstance(raw_interpretations, list):
            raw_interpretations = []

    except Exception as e:
        # Safe Failure Handling (Section 08): Avoid server crashes if LLM call fails
        raw_interpretations = []

    # Run deterministic guardrails over the LLM output
    final_directives = apply_guardrails(
        raw_interpretations=raw_interpretations,
        num_notes=len(operator_notes),
        battery_capacity=battery_capacity
    )

    return final_directives

# ------------------------------------------------------------------
# 4. LOCAL TESTING / EXAMPLE USAGE
# ------------------------------------------------------------------

if __name__ == "__main__":
    # Test case from Problem Statement Section 7.4
    sample_notes = [
        "Solar output will drop to about 20% from 1 PM to 3 PM.",
        "Do not charge the battery between 2 PM and 4 PM.",
        "The cafeteria menu changes tomorrow."
    ]
    sample_battery_capacity = 500.0

    print("Running LLM Interpretation & Guardrail Check...")
    results = interpret_operator_notes(sample_notes, sample_battery_capacity)
    print(json.dumps(results, indent=2))
