"""
llm_client.py
-------------
Operator notes ke structured directives-e convert kore, using Google Gemini.

System prompt (strict JSON-mode):
- LLM-ke bologe "respond ONLY with JSON, no prose"
- 6 types er ekta list provide kora hoy schema hisebe
- For each note -> returns {applies, directive_type, structured_adjustment, explanation}

Robustness:
- 1 ta try parse -> JSON
- fail hoile, text theke JSON block extract kore ({...} match) ar try again
- Last-resort fallback: empty interpretations list
"""

from __future__ import annotations

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv

# load .env from project root
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

try:
    from google import genai
except Exception:  # pragma: no cover
    genai = None


SYSTEM_INSTRUCTION = """You are an assistant that interprets short operator notes about a campus microgrid.

Context:
- 24-hour energy optimization problem for a campus with grid, solar, and battery.
- For each note you must return ONE interpretation object.

Allowed directive_type values (exact strings):
1. "solar_reduction"      -> structured_adjustment = {"start_hour": int 0..23, "end_hour": int 0..23, "factor": float 0..1}
2. "minimum_battery_reserve" -> structured_adjustment = {"value_kwh": float >= 0}
3. "no_charge_window"     -> structured_adjustment = {"start_hour": int 0..23, "end_hour": int 0..23}
4. "no_discharge_window"  -> structured_adjustment = {"start_hour": int 0..23, "end_hour": int 0..23}
5. "max_grid_window"      -> structured_adjustment = {"start_hour": int 0..23, "end_hour": int 0..23, "max_kwh_per_hour": float >= 0}
6. "no_op"                -> structured_adjustment = null  (used when the note is irrelevant, vague, OR a distractor)

Rules:
- If a note is vague, irrelevant, social/personal, or about cafeteria/menu/etc., set applies=false and directive_type="no_op".
- If a note mentions a time range without exact hours, infer reasonable integers 0..23. Use approximate 24h convention (e.g. "1pm to 3pm" = 13..15).
- end_hour must be >= start_hour; clamp to 0..23.
- factor for solar_reduction must be between 0 and 1 (e.g. 0.3 means "only 30% of forecast").
- explanation should be one short sentence in the same language as the note (Bangla or English).

Output format (return ONLY this JSON, no markdown, no commentary):
{
  "interpretations": [
    {
      "note_index": <int>,
      "applies": <true|false>,
      "directive_type": "<one of the 6 above>",
      "structured_adjustment": <object or null>,
      "explanation": "<short string>"
    },
    ...
  ]
}
"""


def _build_user_prompt(notes: List[str]) -> str:
    lines = ["Notes:"]
    for i, n in enumerate(notes):
        lines.append(f"{i}. {n}")
    lines.append("")
    lines.append(
        'Return ONLY JSON like {"interpretations": [...]}. '
        "One entry per note, in the same order. note_index must match the input index."
    )
    return "\n".join(lines)


def _extract_json(text: str) -> Optional[Dict]:
    """Try to find the first {...} block in `text` and parse it."""
    # strip code fences if any
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    # first top-level { ... } pair
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return None


def _fallback_notes_only(notes: List[str]) -> Dict:
    """LLM-fail-safe: all notes treated as no_op, default structure."""
    return {
        "interpretations": [
            {
                "note_index": i,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "LLM unreachable or returned non-JSON; treated as no-op.",
            }
            for i in range(len(notes))
        ]
    }


DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.1-pro-preview"]

# 503-r jonne max attempts per model
MAX_ATTEMPTS_PER_MODEL = 3


def _call_once(client, model: str, notes: List[str], timeout_sec: float = 30.0) -> str:
    """Single Gemini call -> raw text (may be empty on failure)."""
    resp = client.models.generate_content(
        model=model,
        contents=_build_user_prompt(notes),
        config={
            "system_instruction": SYSTEM_INSTRUCTION,
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "automatic_function_calling": {"disable": True},
            "http_options": {"timeout": timeout_sec * 1000},  # ms
        },
    )
    return (resp.text or "").strip()


def interpret_notes(notes: List[str], model: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns a dict like {"interpretations": [...]}.
    Never raises; on any failure returns a safe fallback so guardrail can normalize it.
    """
    if not notes:
        return {"interpretations": []}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return _fallback_notes_only(notes)

    client = genai.Client(api_key=api_key)
    last_err: Optional[str] = None
    candidates = [model] if model else FALLBACK_MODELS

    import time
    for m in candidates:
        for attempt in range(MAX_ATTEMPTS_PER_MODEL):
            try:
                text = _call_once(client, m, notes)
                parsed = _extract_json(text)
                if parsed is not None and "interpretations" in parsed:
                    return parsed
                last_err = f"empty/unparsable JSON from {m} (attempt {attempt+1})"
            except Exception as e:
                msg = str(e)
                last_err = f"{type(e).__name__}: {msg[:200]} from {m} (attempt {attempt+1})"
                # 503 / 429 / "high demand" -> wait
                if "503" in msg or "429" in msg or "UNAVAILABLE" in msg or "high demand" in msg.lower():
                    wait = min(2 ** attempt * 2, 16)  # 2, 4, 8 sec
                    time.sleep(wait)
                    continue
                # other errors: try next model immediately
                break
            # if we got here text was OK structurally -> we returned
        # exhausted attempts for this model -> try next model
        time.sleep(1)

    print(f"[llm_client] all Gemini attempts failed; last_err={last_err}", flush=True)
    return _fallback_notes_only(notes)


def _selftest() -> None:
    # Force-fallback (no real API call if env empty)
    out = interpret_notes(["দুপুর ১টা থেকে ৩টা সোলার কম থাকবে",
                            "Cafeteria menu change", "battery at least 30 kWh"])
    print("selftest out:", json.dumps(out, indent=2)[:400], "...")


if __name__ == "__main__":
    _selftest()
