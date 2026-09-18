# ⚡ BUP Campus Energy Optimization API

**BUP Smart Campus Energy Scheduler** — A Natural-Language-Driven Linear Programming API that turns free-form operator notes into an optimal, physics-validated 24-hour energy schedule.

---

## 🎯 Problem

Campus micro-grids (solar + battery + grid) need careful hour-by-hour scheduling to minimize electricity cost. Operators usually have **soft preferences** in natural language (Bengali or English) such as:

- *"দুপুর ১টা থেকে ৩টা পর্যন্ত সোলার ৩০% কমাও"* (reduce solar 30% during 1–3 PM)
- *"ব্যাটারিতে কমপক্ষে ৩০ kWh রাখো"* (keep ≥30 kWh battery reserve)
- *"রাত ৯টা–১১টা ব্যাটারি চার্জ করো না"* (no charging between 9–11 PM)
- *"পিক আওয়ারে গ্রিড ৮০ কিলোওয়াটের বেশি দিও না"* (no grid above 80 kW during peak)

These are **fuzzy, ambiguous, optional constraints**. Converting them reliably into a working optimizer (LP / MIP) without breaking physical feasibility is the hard part.

---

## 💡 Solution

A 4-stage pipeline:

```
Operator notes  →  [1] LLM interpret  →  [2] Guardrail validate  →
[3] Apply directives  →  [4] LP optimize  →  Validated schedule
```

| Stage | Module | Purpose |
|---|---|---|
| 1 | `llm_client.py` | Gemini `gemini-3.6-flash` (JSON-mode) parses notes into 6 directive types with retry + fallback model + safe `no_op` on failure |
| 2 | `guardrail.py` | Deterministic clamp/pad/coerce — hour 0-23, factor 0-1, value ≥0, unknown types → `no_op` |
| 3 | `main.py` | Apply directives to scenario (override `solar_forecast`, set `min_battery`, set charge/discharge masks, max-grid caps) |
| 4 | `optimizer.py` | scipy `linprog` (HiGHS) with 5 vars × 24h — energy balance, battery dynamics, day-end cyclic, solar cap |

After optimization a **post-validator** checks physics: per-hour energy balance (`g + s + discharge == demand + charge`) and battery cyclic (`batt[24] == initial`).

---

## 🔌 Endpoints

### `GET /health`
Returns liveness check.
```json
{ "status": "ok" }
```

### `POST /optimize-energy`
Request body:
```json
{
  "hours": [
    {"hour": 0,  "demand_kwh": 80,  "solar_kwh": 0,  "tariff_bdt_per_kwh": 8.5},
    ... 24 hours total ...
  ],
  "battery": {"capacity_kwh": 100, "initial_kwh": 40, "max_charge_kw": 30, "max_discharge_kw": 30, "charge_eff": 0.95, "discharge_eff": 0.95},
  "operator_notes": ["dudh", "doi", "ব্যাটারিতে ৩০ kWh রিজার্ভ রাখো", "ক্যাফেটেরিয়া মেনু"]
}
```

Response (200 OK):
```json
{
  "directive_interpretation": [
    {"note_index": 0, "original": "...", "type": "no_op", "applies": false, "explanation": "..."},
    {"note_index": 1, "original": "...", "type": "no_op", "applies": false, "explanation": "..."},
    {"note_index": 2, "original": "ব্যাটারিতে ৩০ kWh...", "type": "minimum_battery_reserve", "applies": true, "adjustment": {"value_kwh": 30.0}, "explanation": "..."},
    {"note_index": 3, "original": "...", "type": "no_op", "applies": false, "explanation": "cafeteria distractor"}
  ],
  "hourly_plan": [
    {"hour": 0, "grid_kwh": 25, "solar_kwh": 0, "battery_kwh": 0, "battery_discharge_kwh": 15, "battery_level_after_kwh": 40, "action": "discharging"},
    ... 24 entries ...
  ],
  "totals": {"total_grid_kwh": 1297.0, "total_cost_bdt": 13526.0, "peak_grid_kwh": 85.0},
  "summary": "Schedule satisfies physics and operator directives."
}
```

---

## 📁 Project Structure

```
D:\Deshneta\
├── main.py             # FastAPI app: /health, /optimize-energy
├── models.py           # Pydantic schemas (request + response)
├── optimizer.py        # LP solver (scipy linprog)
├── guardrail.py        # LLM output validator
├── llm_client.py       # Gemini integration + retry/backoff
├── run_server.py       # uvicorn entry (port 8000)
├── _e2e.py             # end-to-end test via TestClient
├── .env                # GEMINI_API_KEY
└── README.md           # this file
```

---

## 🚀 How to Run

### 1. Install
```powershell
cd D:\Deshneta
pip install fastapi uvicorn pydantic scipy httpx python-dotenv google-genai
```

### 2. Configure API key
`.env` file at project root:
```
GEMINI_API_KEY=your_key_here
```

### 3. Start server
```powershell
python run_server.py
```
Server runs on `http://127.0.0.1:8000`.

- Swagger UI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

### 4. Run E2E test
```powershell
python -u _e2e.py
```
Returns `200 OK` with full pipeline output.

---

## 🧪 Supported Operator Directives

| Type | Example (Bengali) | Adjustment |
|---|---|---|
| `solar_reduction` | দুপুর ১টা–৩টা সোলার ৩০% | `{start_hour, end_hour, factor}` |
| `minimum_battery_reserve` | ব্যাটারিতে ৩০ kWh রিজার্ভ | `{value_kwh}` |
| `no_charge_window` | রাত ৯টা–১১টা চার্জ নিষেধ | `{start_hour, end_hour}` |
| `no_discharge_window` | রাত ১২টা–৬টা ডিসচার্জ নিষেধ | `{start_hour, end_hour}` |
| `max_grid_window` | পিকে গ্রিড ৮০ kW এর বেশি না | `{start_hour, end_hour, max_kwh}` |
| `no_op` | ক্যাফেটেরিয়া মেনু | `{}` (distractor or unrelated) |

---

## ✅ Quality Features

- **Physics validation**: per-hour energy balance + day-end battery cyclic constraint
- **Guardrail**: clamps hour/factor, pads missing entries, coerces malformed output
- **LLM resilience**: 3-attempt retry + exponential backoff + fallback model chain + safe `no_op` fallback
- **Bilingual**: handles Bengali + English notes
- **Edge cases**: empty notes, distractors, invalid directives all degrade gracefully

---

## 📊 Sample Output

| Metric | Value |
|---|---|
| Status | `200 OK` |
| Total grid | `1297 kWh` |
| Total cost | `BDT 13,526` |
| Peak grid | `85 kWh` |
| Validator | ✅ physics + directives satisfied |

---

## 🛠 Tech Stack

- **Python 3.14** + FastAPI 0.141 + Pydantic 2.13
- **scipy 1.18** (linprog, HiGHS)
- **google-genai 2.24** (Gemini 3.6 Flash, JSON-mode)
- **python-dotenv** for `.env` loading
