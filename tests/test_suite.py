"""
Comprehensive test suite for Smart Campus Energy Optimization Service.
Covers:
- Request/Response validation
- LLM & Semantic Fallback Interpretation
- Paraphrase robustness
- Deterministic Guardrails
- Mathematical Linear Programming Solver
- Energy balance, battery bounds, neutrality, rate limits
- FastAPI HTTP Endpoints (/health, /optimize-energy)
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from schemas import (
    OptimizeRequest,
    HourEntry,
    BatteryConfig,
    DirectiveInterpretationEntry
)
from guardrails import (
    validate_and_guard_directives,
    sanitize_hours,
    validate_directive_entry
)
from interpreter import (
    extract_hours_from_text,
    fallback_semantic_parser
)
from optimizer import solve_energy_optimization
from verifier import verify_and_recalculate_schedule
from main import app


@pytest.fixture
def sample_battery():
    return BatteryConfig(
        capacity_kwh=500.0,
        initial_energy_kwh=200.0,
        minimum_energy_kwh=50.0,
        max_charge_kwh_per_hour=100.0,
        max_discharge_kwh_per_hour=100.0
    )


@pytest.fixture
def sample_hours():
    # 24-hour synthetic profile
    # Morning: low solar, cheap tariff
    # Afternoon: high solar, medium tariff
    # Evening: zero solar, peak tariff
    hours = []
    for h in range(24):
        demand = 150.0 + (30.0 if 8 <= h <= 20 else 0.0)
        solar = 120.0 if 10 <= h <= 15 else (50.0 if 8 <= h <= 17 else 0.0)
        tariff = 12.0 if 17 <= h <= 21 else (6.0 if 0 <= h <= 6 else 8.0)
        hours.append(HourEntry(
            hour=h,
            demand_kwh=demand,
            solar_kwh=solar,
            tariff_bdt_per_kwh=tariff
        ))
    return hours


# ---------------------------------------------------------------------------
# 1. Hours Extraction & Semantic Interpretation Tests
# ---------------------------------------------------------------------------

def test_extract_hours_half_open():
    # "1 PM to 3 PM" -> [13, 14]
    assert extract_hours_from_text("Solar will drop from 1 PM to 3 PM.") == [13, 14]
    # "between 2 PM and 4 PM" -> [14, 15]
    assert extract_hours_from_text("Do not charge between 2 PM and 4 PM.") == [14, 15]
    # "from 6 PM until 9 PM" -> [18, 19, 20]
    assert extract_hours_from_text("Keep reserve from 6 PM until 9 PM.") == [18, 19, 20]
    # "1-3 PM" -> [13, 14]
    assert extract_hours_from_text("Maintenance during 1-3 PM window.") == [13, 14]
    # "13:00 to 15:00" -> [13, 14]
    assert extract_hours_from_text("Drop between 13:00 and 15:00.") == [13, 14]


def test_fallback_semantic_parser_all_types(sample_battery):
    notes = [
        "Solar output will drop to about 20% from 1 PM to 3 PM.",
        "Do not charge the battery between 2 PM and 4 PM.",
        "The cafeteria menu changes tomorrow."
    ]
    results = fallback_semantic_parser(notes, sample_battery)
    assert len(results) == 3

    # Note 0: solar_reduction
    assert results[0]["applies"] is True
    assert results[0]["directive_type"] == "solar_reduction"
    assert results[0]["structured_adjustment"]["hours"] == [13, 14]
    assert abs(results[0]["structured_adjustment"]["factor"] - 0.2) < 1e-4

    # Note 1: no_charge_window
    assert results[1]["applies"] is True
    assert results[1]["directive_type"] == "no_charge_window"
    assert results[1]["structured_adjustment"]["hours"] == [14, 15]

    # Note 2: no_op
    assert results[2]["applies"] is False
    assert results[2]["directive_type"] == "no_op"
    assert results[2]["structured_adjustment"] is None


def test_paraphrase_robustness(sample_battery):
    # Paraphrase 1: "PV production will drop to about 20% between 13:00 and 15:00."
    p1 = fallback_semantic_parser(["PV production will drop to about 20% between 13:00 and 15:00."], sample_battery)[0]
    # Paraphrase 2: "Expect an 80% reduction in rooftop solar during the 1-3 PM maintenance window."
    p2 = fallback_semantic_parser(["Expect an 80% reduction in rooftop solar during the 1-3 PM maintenance window."], sample_battery)[0]
    # Paraphrase 3: "Panel washing from one until three will leave roughly one-fifth of normal solar output."
    p3 = fallback_semantic_parser(["Panel washing from one until three will leave roughly one-fifth of normal solar output."], sample_battery)[0]

    for p in [p1, p2, p3]:
        assert p["applies"] is True
        assert p["directive_type"] == "solar_reduction"
        assert p["structured_adjustment"]["hours"] == [13, 14]
        assert abs(p["structured_adjustment"]["factor"] - 0.2) < 0.05


# ---------------------------------------------------------------------------
# 2. Guardrails Tests
# ---------------------------------------------------------------------------

def test_sanitize_hours():
    assert sanitize_hours([15, 13, 14]) == [13, 14, 15]
    assert sanitize_hours([13, 13, 14]) == [13, 14]
    with pytest.raises(ValueError):
        sanitize_hours([-1, 5])
    with pytest.raises(ValueError):
        sanitize_hours([24])


def test_guardrails_invalid_directive_falls_back(sample_battery):
    malformed_entry = {
        "note_index": 0,
        "applies": True,
        "directive_type": "hallucinated_magic_power",
        "structured_adjustment": {"hours": [1, 2]}
    }
    validated = validate_directive_entry(malformed_entry, 0, sample_battery)
    assert validated.applies is False
    assert validated.directive_type == "no_op"
    assert validated.structured_adjustment is None


def test_guardrails_bounds_enforcement(sample_battery):
    # Factor > 1.0 falls back to no_op
    bad_solar = {
        "note_index": 0,
        "applies": True,
        "directive_type": "solar_reduction",
        "structured_adjustment": {"hours": [1, 2], "factor": 1.5}
    }
    v1 = validate_directive_entry(bad_solar, 0, sample_battery)
    assert v1.directive_type == "no_op"

    # Reserve > capacity falls back to no_op
    bad_reserve = {
        "note_index": 0,
        "applies": True,
        "directive_type": "minimum_battery_reserve",
        "structured_adjustment": {"hours": [1, 2], "minimum_energy_kwh": 9999.0}
    }
    v2 = validate_directive_entry(bad_reserve, 0, sample_battery)
    assert v2.directive_type == "no_op"


# ---------------------------------------------------------------------------
# 3. Mathematical Optimizer & Replay Verification Tests
# ---------------------------------------------------------------------------

def test_optimizer_and_verifier_pipeline(sample_battery, sample_hours):
    req = OptimizeRequest(
        scenario_id="TEST-SCENARIO-01",
        operator_notes=[
            "Solar output will drop to about 20% from 1 PM to 3 PM.",
            "Do not charge the battery between 2 PM and 4 PM."
        ],
        hours=sample_hours,
        battery=sample_battery
    )

    directives = [
        DirectiveInterpretationEntry(
            note_index=0,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [13, 14], "factor": 0.2},
            explanation="Solar reduced"
        ),
        DirectiveInterpretationEntry(
            note_index=1,
            applies=True,
            directive_type="no_charge_window",
            structured_adjustment={"hours": [14, 15]},
            explanation="No charge"
        )
    ]

    hourly_plan = solve_energy_optimization(req, directives)
    assert len(hourly_plan) == 24

    # Check no charge window was obeyed
    for h in [14, 15]:
        assert hourly_plan[h].battery_action != "charge"
        if hourly_plan[h].battery_action == "idle":
            assert hourly_plan[h].battery_kwh == 0.0

    # Schedule Replay Verification
    total_grid, total_cost, peak_grid, plan_summary = verify_and_recalculate_schedule(
        req, directives, hourly_plan
    )

    assert total_grid > 0
    assert total_cost > 0
    assert peak_grid > 0
    # End of day neutrality
    assert abs(hourly_plan[23].battery_energy_after_kwh - sample_battery.initial_energy_kwh) < 0.05


# ---------------------------------------------------------------------------
# 4. HTTP API Endpoints Tests
# ---------------------------------------------------------------------------

def test_api_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_optimize_energy_end_to_end(sample_battery, sample_hours):
    client = TestClient(app)
    payload = {
        "scenario_id": "GRID-101",
        "operator_notes": [
            "Solar output will drop to about 20% from 1 PM to 3 PM.",
            "Do not charge the battery between 2 PM and 4 PM.",
            "The cafeteria menu changes tomorrow."
        ],
        "hours": [h.model_dump() for h in sample_hours],
        "battery": sample_battery.model_dump()
    }

    response = client.post("/optimize-energy", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["scenario_id"] == "GRID-101"
    assert len(data["directive_interpretation"]) == 3
    assert len(data["hourly_plan"]) == 24
    assert data["total_grid_kwh"] > 0
    assert data["total_cost_bdt"] > 0
    assert data["peak_grid_kwh"] > 0
    assert "plan_summary" in data

    # Check directive interpretations
    interp = data["directive_interpretation"]
    assert interp[0]["directive_type"] == "solar_reduction"
    assert interp[0]["applies"] is True
    assert interp[1]["directive_type"] == "no_charge_window"
    assert interp[1]["applies"] is True
    assert interp[2]["directive_type"] == "no_op"
    assert interp[2]["applies"] is False
    assert interp[2]["structured_adjustment"] is None


def test_api_invalid_request_returns_400():
    client = TestClient(app)
    # Missing hours and battery
    response = client.post("/optimize-energy", json={"scenario_id": "BAD"})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# 5. Advanced Edge Cases & Constraint Enforcement Tests
# ---------------------------------------------------------------------------

def test_max_grid_window_enforcement(sample_battery, sample_hours):
    req = OptimizeRequest(
        scenario_id="TEST-GRID-CAP",
        operator_notes=["Grid import may not exceed 100 kWh between 17:00 and 20:00."],
        hours=sample_hours,
        battery=sample_battery
    )
    directives = [
        DirectiveInterpretationEntry(
            note_index=0,
            applies=True,
            directive_type="max_grid_window",
            structured_adjustment={"hours": [17, 18, 19], "max_grid_kwh": 100.0},
            explanation="Cap grid import to 100 kWh."
        )
    ]
    hourly_plan = solve_energy_optimization(req, directives)
    for h in [17, 18, 19]:
        assert hourly_plan[h].grid_kwh <= 100.05, f"Hour {h} exceeded max grid cap: {hourly_plan[h].grid_kwh}"


def test_no_discharge_window_enforcement(sample_battery, sample_hours):
    req = OptimizeRequest(
        scenario_id="TEST-NO-DISCHARGE",
        operator_notes=["Battery discharging is unavailable from 6 PM to 9 PM."],
        hours=sample_hours,
        battery=sample_battery
    )
    directives = [
        DirectiveInterpretationEntry(
            note_index=0,
            applies=True,
            directive_type="no_discharge_window",
            structured_adjustment={"hours": [18, 19, 20]},
            explanation="No discharge window"
        )
    ]
    hourly_plan = solve_energy_optimization(req, directives)
    for h in [18, 19, 20]:
        assert hourly_plan[h].battery_action != "discharge", f"Hour {h} discharged during no_discharge_window"


def test_minimum_battery_reserve_enforcement(sample_battery, sample_hours):
    req = OptimizeRequest(
        scenario_id="TEST-RESERVE",
        operator_notes=["Keep at least 250 kWh in reserve from 6 PM until 9 PM."],
        hours=sample_hours,
        battery=sample_battery
    )
    directives = [
        DirectiveInterpretationEntry(
            note_index=0,
            applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": [18, 19, 20], "minimum_energy_kwh": 250.0},
            explanation="Maintain reserve"
        )
    ]
    hourly_plan = solve_energy_optimization(req, directives)
    for h in [18, 19, 20]:
        assert hourly_plan[h].battery_energy_after_kwh >= 249.95, f"Hour {h} fell below required reserve: {hourly_plan[h].battery_energy_after_kwh}"


def test_end_of_day_neutrality_strict(sample_battery, sample_hours):
    # Test across multiple initial energies
    for init_e in [100.0, 200.0, 350.0]:
        bat = BatteryConfig(
            capacity_kwh=500.0,
            initial_energy_kwh=init_e,
            minimum_energy_kwh=50.0,
            max_charge_kwh_per_hour=100.0,
            max_discharge_kwh_per_hour=100.0
        )
        req = OptimizeRequest(
            scenario_id=f"TEST-NEUTRALITY-{int(init_e)}",
            operator_notes=["Informational note"],
            hours=sample_hours,
            battery=bat
        )
        directives = [
            DirectiveInterpretationEntry(
                note_index=0,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation="No-op"
            )
        ]
        plan = solve_energy_optimization(req, directives)
        assert abs(plan[23].battery_energy_after_kwh - init_e) < 0.01

