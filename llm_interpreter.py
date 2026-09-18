"""Gemini-backed operator-note interpretation for GridWise.

The model chooses the meaning of a note.  ``directives.validate_directive_interpretations``
then decides whether that output is safe to use.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel

from app.directives import DirectiveValidationError, validate_directive_interpretations


class LLMInterpretationError(RuntimeError):
    """A controlled failure that the API layer can turn into a safe response."""


SYSTEM_INSTRUCTIONS = """You are the GridWise operator-note interpreter.
Interpret every operator note for one 24-hour campus energy schedule. Return exactly
one directive for each input note in note_index order, starting at 0.

The only directive types are:
- solar_reduction: usable solar becomes a remaining factor during listed hours.
- minimum_battery_reserve: battery energy after listed hours must be at least a value.
- no_charge_window: battery charge is prohibited during listed hours.
- no_discharge_window: battery discharge is prohibited during listed hours.
- max_grid_window: grid import cannot exceed a value during listed hours.
- no_op: the note does not affect this energy schedule.

Rules:
- Use no_op only for irrelevant notes. no_op has applies=false and adjustment=null.
- Every non-no_op directive has applies=true.
- Time windows use whole hours: start is included and end is excluded. 1 PM to 3 PM
  is [13, 14]. Use 0 for midnight and 23 for 11 PM.
- For solar_reduction, factor is the usable fraction left. An 80% reduction means
  factor 0.2.
- Do not invent demand, tariffs, battery limits, hours, numbers, or new directive types.
- Return only the required JSON object. Keep explanations short.
"""


class _RawDirective(BaseModel):
    """The constrained outer shape requested from Gemini.

    The next validation layer remains deliberately stricter: it checks the
    directive-specific adjustment shape and every challenge numeric rule.
    """

    note_index: int
    applies: bool
    directive_type: Literal[
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
    ]
    structured_adjustment: dict[str, Any] | None
    explanation: str


class _RawDirectiveEnvelope(BaseModel):
    directives: list[_RawDirective]


def interpret_and_validate_notes(
    operator_notes: list[str],
    *,
    battery_capacity_kwh: float,
    model: str | None = None,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    """Use an LLM, then return only deterministic-validator-approved directives."""
    _validate_operator_notes(operator_notes)
    raw_output = interpret_operator_notes(operator_notes, model=model, client=client)
    try:
        return validate_directive_interpretations(
            raw_output,
            note_count=len(operator_notes),
            battery_capacity_kwh=battery_capacity_kwh,
        )
    except DirectiveValidationError as exc:
        raise LLMInterpretationError(
            "The model returned an invalid directive interpretation."
        ) from exc


def interpret_operator_notes(
    operator_notes: list[str], *, model: str | None = None, client: Any | None = None
) -> dict[str, Any]:
    """Call Gemini Structured Outputs and return its JSON object.

    ``client`` is injectable so the API call can be tested without a real key.
    """
    _validate_operator_notes(operator_notes)
    selected_model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    if client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise LLMInterpretationError("GEMINI_API_KEY is not configured.")
        try:
            from google import genai
        except ImportError as exc:
            raise LLMInterpretationError(
                "Gemini SDK is not installed. Add the google-genai package to requirements.txt."
            ) from exc
        client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model=selected_model,
            contents=json.dumps({"operator_notes": operator_notes}, ensure_ascii=False),
            config={
                "system_instruction": SYSTEM_INSTRUCTIONS,
                "response_mime_type": "application/json",
                "response_schema": _RawDirectiveEnvelope,
                "temperature": 0,
            },
        )
    except Exception as exc:
        raise LLMInterpretationError("The LLM provider could not interpret the notes.") from exc

    output_text = getattr(response, "text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise LLMInterpretationError("The LLM did not return an interpretation.")
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise LLMInterpretationError("The LLM returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise LLMInterpretationError("The LLM returned an invalid response shape.")
    return parsed


def _validate_operator_notes(operator_notes: Any) -> None:
    if not isinstance(operator_notes, list) or not 1 <= len(operator_notes) <= 3:
        raise ValueError("operator_notes must be a list containing 1 to 3 notes")
    if any(not isinstance(note, str) or not note.strip() for note in operator_notes):
        raise ValueError("operator_notes must contain only non-empty strings")
