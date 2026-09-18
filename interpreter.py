"""
LLM Operator Note Interpreter for Smart Campus Energy Optimization Challenge.
Uses Google Gemini API (google-genai SDK) with a structured prompt, backed by a comprehensive
rule-based semantic NLP fallback for offline reliability and extreme robustness.
"""

import os
import re
import json
import logging
from typing import Any, Dict, List, Optional
from schemas import BatteryConfig

logger = logging.getLogger("energy_interpreter")

SYSTEM_INSTRUCTION = """You are an expert energy scheduling assistant for the BUP Smart Campus Energy System.
Your task is to analyze 1 to 3 campus operator notes and translate each note into a structured directive.
Each scenario covers a 24-hour horizon (hours 0 through 23).

You must map each note to EXACTLY ONE of these 6 directive types:
1. "solar_reduction":
   Usable rooftop solar output is reduced during specific hours.
   structured_adjustment: {"hours": [sorted unique integers 0..23], "factor": number between 0.0 and 1.0}
   CRITICAL: "factor" is the USABLE FRACTION REMAINING!
   Examples:
   - "Solar output will drop to about 20% from 1 PM to 3 PM" -> factor = 0.2, hours = [13, 14]
   - "Expect an 80% reduction in rooftop solar from 1 PM to 3 PM" -> factor = 0.2 (100% - 80% = 20% remaining), hours = [13, 14]
   - "Leave roughly one-fifth of normal solar output" -> factor = 0.2, hours = [13, 14]

2. "minimum_battery_reserve":
   The battery storage must maintain at least a given energy level during specific hours.
   structured_adjustment: {"hours": [sorted unique integers 0..23], "minimum_energy_kwh": number >= 0}
   Example:
   - "Keep at least 120 kWh in reserve from 6 PM until 9 PM." -> hours = [18, 19, 20], minimum_energy_kwh = 120.0

3. "no_charge_window":
   Battery charging is disallowed during specific hours.
   structured_adjustment: {"hours": [sorted unique integers 0..23]}
   Example:
   - "Do not charge the battery between 2 PM and 4 PM." -> hours = [14, 15]

4. "no_discharge_window":
   Battery discharging is disallowed during specific hours.
   structured_adjustment: {"hours": [sorted unique integers 0..23]}
   Example:
   - "Battery discharging is unavailable from 8 AM to 11 AM." -> hours = [8, 9, 10]

5. "max_grid_window":
   Grid import cannot exceed a stated amount during specific hours.
   structured_adjustment: {"hours": [sorted unique integers 0..23], "max_grid_kwh": number >= 0}
   Example:
   - "Grid import may not exceed 50 kWh between 5 PM and 8 PM." -> hours = [17, 18, 19], max_grid_kwh = 50.0

6. "no_op":
   The note is a distractor, informational, or does not affect the current 24-hour energy schedule.
   applies: false
   structured_adjustment: null
   Examples:
   - "The cafeteria menu changes tomorrow." -> no_op
   - "The Dean has scheduled an all-hands meeting in the auditorium at 3 PM." -> no_op

IMPORTANT TIME CONVENTIONS:
- Hours are whole-hour intervals [start_hour, end_hour) where start is INCLUDED and end is EXCLUDED.
- "1 PM to 3 PM" -> [13, 14]
- "2 PM to 4 PM" -> [14, 15]
- "6 PM until 9 PM" -> [18, 19, 20]
- "13:00 to 15:00" -> [13, 14]
- "one until three" -> [13, 14]

RULES:
- Return valid JSON: a list of objects in exact note_index order (0, 1, ... N-1).
- For no_op: "applies" must be false, "structured_adjustment" must be null.
- For all other directives: "applies" must be true, "structured_adjustment" must be non-null matching the schema.
- Do not invent demand, solar, tariff, or battery limit changes.
"""


def _parse_time_word_or_number(text: str) -> Optional[int]:
    """Converts a word or string representation of a time/hour to integer 0..23."""
    text = text.strip().lower()
    word_map = {
        "midnight": 0, "noon": 12,
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12
    }
    
    # Check 12-hour format with am/pm
    m_ampm = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", text)
    if m_ampm:
        hr = int(m_ampm.group(1))
        meridiem = m_ampm.group(3)
        if meridiem == "pm" and hr != 12:
            hr += 12
        elif meridiem == "am" and hr == 12:
            hr = 0
        return hr

    # Check 24-hour format e.g. 13:00 or 13
    m_24 = re.match(r"^(\d{1,2})(?::00)?$", text)
    if m_24:
        hr = int(m_24.group(1))
        if 0 <= hr <= 23:
            return hr

    # Check words with am/pm e.g. "one pm"
    m_word_ampm = re.match(r"^(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*(am|pm)$", text)
    if m_word_ampm:
        hr = word_map[m_word_ampm.group(1)]
        meridiem = m_word_ampm.group(2)
        if meridiem == "pm" and hr != 12:
            hr += 12
        elif meridiem == "am" and hr == 12:
            hr = 0
        return hr

    if text in word_map:
        return word_map[text]

    return None


def extract_hours_from_text(note: str) -> List[int]:
    """
    Extracts whole-hour half-open [start, end) time interval from natural language.
    E.g. '1 PM to 3 PM' -> [13, 14]
         'between 13:00 and 15:00' -> [13, 14]
         '1-3 PM' -> [13, 14]
         '6 PM until 9 PM' -> [18, 19, 20]
    """
    note_lower = note.lower()

    # Pattern: 1-3 PM or 1 - 3 PM
    m_dash = re.search(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s*(am|pm)\b", note_lower)
    if m_dash:
        s_val = int(m_dash.group(1))
        e_val = int(m_dash.group(2))
        meridiem = m_dash.group(3)
        if meridiem == "pm":
            if s_val != 12:
                s_val += 12
            if e_val != 12:
                e_val += 12
        elif meridiem == "am":
            if s_val == 12:
                s_val = 0
            if e_val == 12:
                e_val = 0
        if 0 <= s_val < e_val <= 24:
            return list(range(s_val, min(24, e_val)))

    # Pattern: [from/between] (start) [to/until/and] (end)
    patterns = [
        r"(?:from|between|during)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|[a-z]+\s*(?:am|pm)?)\s*(?:to|until|and|-)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|[a-z]+\s*(?:am|pm)?)"
    ]

    for pat in patterns:
        for m in re.finditer(pat, note_lower):
            s_raw = m.group(1).strip()
            e_raw = m.group(2).strip()
            # If start doesn't have am/pm but end does (e.g. "from 1 to 3 PM")
            if not re.search(r"am|pm", s_raw) and re.search(r"am|pm", e_raw):
                ampm = re.search(r"am|pm", e_raw).group(0)
                s_raw = f"{s_raw} {ampm}"

            s_hr = _parse_time_word_or_number(s_raw)
            e_hr = _parse_time_word_or_number(e_raw)

            # If end is smaller than start in 12hr context without am/pm, adjust
            if s_hr is not None and e_hr is not None:
                is_afternoon_context = any(w in note_lower for w in ["afternoon", "pm", "solar", "panel", "pv", "washing", "cleaning", "lunch"])
                is_evening_context = any(w in note_lower for w in ["evening", "night"])

                if s_hr <= 7 and e_hr <= 8 and is_afternoon_context and not ("am" in s_raw or "am" in e_raw):
                    s_hr += 12
                    e_hr += 12
                elif s_hr <= 11 and e_hr <= 12 and is_evening_context and not ("am" in s_raw or "am" in e_raw):
                    s_hr += 12
                    e_hr += 12

                if 0 <= s_hr < e_hr <= 24:
                    return list(range(s_hr, min(24, e_hr)))

    return []


def fallback_semantic_parser(operator_notes: List[str], battery: BatteryConfig) -> List[Dict[str, Any]]:
    """
    Intelligent rule-based semantic parser that guarantees 100% availability
    and handles paraphrased variations if the LLM API is unavailable.
    """
    results = []

    for idx, note in enumerate(operator_notes):
        n_lower = note.lower()
        hours = extract_hours_from_text(note)

        # 1. Check Solar Reduction
        is_solar = any(term in n_lower for term in [
            "solar", "pv ", "pv production", "photovoltaic", "panel washing", "panel cleaning", "rooftop solar"
        ])
        is_reduction = any(term in n_lower for term in [
            "drop", "reduc", "leave", "fall", "one-fifth", "one-half", "percent", "%", "fraction"
        ])

        if is_solar and is_reduction and hours:
            # Determine factor (usable fraction remaining)
            factor = 0.2 # default reasonable factor
            
            # Look for percentage drop/reduction vs drop to X%
            # "drop to about 20%" -> factor = 0.2
            # "80% reduction" -> factor = 0.2 (100 - 80 = 20%)
            # "drop by 80%" -> factor = 0.2
            m_drop_to = re.search(r"(?:drop to|reach|at|about|roughly)\s*(\d{1,3})\s*%", n_lower)
            m_reduc_by = re.search(r"(\d{1,3})\s*%\s*(?:reduction|drop|cut|decrease)", n_lower)
            m_by_reduc = re.search(r"(?:drop by|reduced by|cut by)\s*(\d{1,3})\s*%", n_lower)
            m_fraction_word = re.search(r"(one-fifth|one fifth)", n_lower)
            m_half_word = re.search(r"(half|one-half|one half)", n_lower)

            if m_drop_to:
                pct = float(m_drop_to.group(1))
                factor = pct / 100.0
            elif m_reduc_by:
                pct = float(m_reduc_by.group(1))
                factor = max(0.0, (100.0 - pct) / 100.0)
            elif m_by_reduc:
                pct = float(m_by_reduc.group(1))
                factor = max(0.0, (100.0 - pct) / 100.0)
            elif m_fraction_word:
                factor = 0.2
            elif m_half_word:
                factor = 0.5
            else:
                m_pct = re.search(r"(\d{1,3})\s*%", n_lower)
                if m_pct:
                    pct = float(m_pct.group(1))
                    if "reduction" in n_lower or "drop" in n_lower:
                        if pct > 50:
                            factor = (100.0 - pct) / 100.0
                        else:
                            factor = pct / 100.0

            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {
                    "hours": hours,
                    "factor": round(factor, 4)
                },
                "explanation": f"Interpreted as solar_reduction for hours {hours} with remaining factor {round(factor, 4)}."
            })
            continue

        # 2. Check Battery Minimum Reserve
        is_reserve = any(term in n_lower for term in [
            "reserve", "keep at least", "maintain at least", "minimum energy", "keep battery", "above"
        ]) and ("kwh" in n_lower or "reserve" in n_lower)

        if is_reserve and hours:
            m_val = re.search(r"(\d+(?:\.\d+)?)\s*kwh", n_lower)
            val = float(m_val.group(1)) if m_val else battery.minimum_energy_kwh
            val = min(val, battery.capacity_kwh)

            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {
                    "hours": hours,
                    "minimum_energy_kwh": round(val, 2)
                },
                "explanation": f"Interpreted as minimum_battery_reserve of {val} kWh for hours {hours}."
            })
            continue

        # 3. Check No Charge Window
        is_no_charge = any(term in n_lower for term in [
            "do not charge", "no charging", "charging is unavailable", "pause charging", "disable charge",
            "avoid charging", "halt charging", "stop charging", "charge unavailable"
        ])
        if is_no_charge and hours:
            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {
                    "hours": hours
                },
                "explanation": f"Interpreted as no_charge_window for hours {hours}."
            })
            continue

        # 4. Check No Discharge Window
        is_no_discharge = any(term in n_lower for term in [
            "do not discharge", "no discharging", "discharging is unavailable", "pause discharge", "disable discharge",
            "avoid discharging", "halt discharge", "stop discharging", "discharge unavailable"
        ])
        if is_no_discharge and hours:
            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "no_discharge_window",
                "structured_adjustment": {
                    "hours": hours
                },
                "explanation": f"Interpreted as no_discharge_window for hours {hours}."
            })
            continue

        # 5. Check Max Grid Window
        is_grid_cap = any(term in n_lower for term in [
            "grid import", "grid purchase", "max grid", "cap grid", "limit grid", "may not exceed"
        ]) and ("kwh" in n_lower or "cap" in n_lower or "limit" in n_lower)

        if is_grid_cap and hours:
            m_val = re.search(r"(\d+(?:\.\d+)?)\s*kwh", n_lower)
            val = float(m_val.group(1)) if m_val else 100.0
            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {
                    "hours": hours,
                    "max_grid_kwh": round(val, 2)
                },
                "explanation": f"Interpreted as max_grid_window of {val} kWh for hours {hours}."
            })
            continue

        # 6. Default: Irrelevant Note -> no_op
        results.append({
            "note_index": idx,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Note contains no campus energy directives; interpreted as no_op."
        })

    return results


async def interpret_operator_notes_llm(
    operator_notes: List[str],
    battery: BatteryConfig
) -> List[Dict[str, Any]]:
    """
    Interprets operator notes using Google Gemini API if GEMINI_API_KEY is present,
    otherwise uses the semantic fallback parser.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.info("No GEMINI_API_KEY detected; using semantic NLP fallback engine.")
        return fallback_semantic_parser(operator_notes, battery)

    prompt = f"""Analyze these campus operator notes:
{json.dumps(operator_notes, indent=2)}

Battery parameters:
- capacity_kwh: {battery.capacity_kwh}
- minimum_energy_kwh: {battery.minimum_energy_kwh}

Return a valid JSON array of objects with fields:
[
  {{
    "note_index": 0,
    "applies": true or false,
    "directive_type": "solar_reduction" | "minimum_battery_reserve" | "no_charge_window" | "no_discharge_window" | "max_grid_window" | "no_op",
    "structured_adjustment": object or null,
    "explanation": "short explanation"
  }}
]
"""

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "response_mime_type": "application/json"
            }
        )

        response_text = response.text
        parsed = json.loads(response_text)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict) and "directives" in parsed and isinstance(parsed["directives"], list):
            return parsed["directives"]
        else:
            logger.warning(f"Unexpected JSON shape from Gemini: {response_text[:200]}")
            return fallback_semantic_parser(operator_notes, battery)

    except Exception as e:
        logger.warning(f"Gemini API call failed ({e}); falling back to semantic parser.")
        return fallback_semantic_parser(operator_notes, battery)
