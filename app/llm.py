import os
import json
from typing import List
from openai import OpenAI
from app.models import DirectiveInterpretation, LLMInterpretationWrapper

SYSTEM_PROMPT = """
You are an expert smart campus energy operator assistant.
Analyze each natural language operator note and map it to exactly one directive entry.

Supported Directive Types & Rules:
1. "solar_reduction":
   - Required structured_adjustment: {"hours": [...], "factor": float}
   - 'factor' is the remaining fraction (e.g., 80% reduction -> factor=0.2).
2. "minimum_battery_reserve":
   - Required structured_adjustment: {"hours": [...], "minimum_energy_kwh": float}
3. "no_charge_window":
   - Required structured_adjustment: {"hours": [...]}
4. "no_discharge_window":
   - Required structured_adjustment: {"hours": [...]}
5. "max_grid_window":
   - Required structured_adjustment: {"hours": [...], "max_grid_kwh": float}
6. "no_op":
   - Required structured_adjustment: null
   - Applies MUST be false.

Global Directive Rules:
- Time windows use 0-23 clock hours. Start hour is included, end hour is excluded. (e.g., "1 PM to 3 PM" -> hours [13, 14]).
- "hours" must be unique integers in strictly ascending order.
- "applies" must be true for all directives EXCEPT "no_op" (which must be false).
- Return exactly one interpretation for every note in note_index order (0 to N-1).
"""

def interpret_operator_notes(notes: List[str]) -> List[DirectiveInterpretation]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    formatted_notes = "\n".join([f"Note {i}: \"{note}\"" for i, note in enumerate(notes)])
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Interpret these notes:\n{formatted_notes}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.0
    )

    content = response.choices[0].message.content
    parsed_json = json.loads(content)
    
    # Handle if response is wrapped or direct list
    if "interpretations" in parsed_json:
        data = parsed_json["interpretations"]
    elif "directive_interpretation" in parsed_json:
        data = parsed_json["directive_interpretation"]
    else:
        data = parsed_json

    return [DirectiveInterpretation(**item) for item in data]