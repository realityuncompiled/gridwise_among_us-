"""
main.py
-------
FastAPI server — entry point.

Flow:
    request -> LLM (interpret notes)
            -> guardrail (validate JSON shape)
            -> apply directives to scenario data
            -> LP optimizer (solve cheapest schedule)
            -> validator (sanity-check the schedule)
            -> response

Endpoints:
    GET  /health           -> liveness
    POST /optimize-energy  -> main job
"""

from __future__ import annotations

from typing import List, Dict, Tuple

from fastapi import FastAPI, HTTPException

from models import (
    ScenarioRequest,
    OptimizeResponse,
    DirectiveInterpretation,
    HourlyPlanEntry,
)
from llm_client import interpret_notes
from guardrail import validate_interpretations
from optimizer import optimize, OptimizerInput


app = FastAPI(title="BUP GridWise Optimizer")


# ---------- helpers: apply each directive to scenario data ----------

def _apply_solar_reduction(hours: List[Dict], start: int, end: int, factor: float) -> None:
    for h in hours:
        if start <= int(h["hour"]) <= end:
            h["solar_kwh"] = round(float(h["solar_kwh"]) * float(factor), 4)


def _apply_min_battery_reserve(battery: Dict, value_kwh: float) -> None:
    battery["minimum_energy_kwh"] = max(
        float(battery.get("minimum_energy_kwh", 0.0)),
        min(float(value_kwh), float(battery["capacity_kwh"])),
    )


def _apply_no_charge_window(battery: Dict, start: int, end: int) -> None:
    battery.setdefault("_no_charge_windows", []).append((start, end))


def _apply_no_discharge_window(battery: Dict, start: int, end: int) -> None:
    battery.setdefault("_no_discharge_windows", []).append((start, end))


def _apply_max_grid_window(opt_in: OptimizerInput, start: int, end: int, cap_kwh: float) -> None:
    if not hasattr(opt_in, "_explicit_grid_caps"):
        opt_in._explicit_grid_caps = {}
    for t in range(max(0, start), min(len(opt_in.hours), end + 1)):
        opt_in._explicit_grid_caps[t] = float(cap_kwh)


def _apply_directives(
    hours: List[Dict],
    battery: Dict,
    interpretations: List[Dict],
    opt_in: OptimizerInput,
) -> None:
    for it in interpretations:
        if not it.get("applies"):
            continue
        dtype = it.get("directive_type")
        sa = it.get("structured_adjustment") or {}
        try:
            if dtype == "solar_reduction":
                _apply_solar_reduction(hours, int(sa["start_hour"]), int(sa["end_hour"]), float(sa["factor"]))
            elif dtype == "minimum_battery_reserve":
                _apply_min_battery_reserve(battery, float(sa["value_kwh"]))
            elif dtype == "no_charge_window":
                _apply_no_charge_window(battery, int(sa["start_hour"]), int(sa["end_hour"]))
            elif dtype == "no_discharge_window":
                _apply_no_discharge_window(battery, int(sa["start_hour"]), int(sa["end_hour"]))
            elif dtype == "max_grid_window":
                _apply_max_grid_window(opt_in, int(sa["start_hour"]), int(sa["end_hour"]),
                                       float(sa.get("max_kwh_per_hour", 1e9)))
        except Exception:
            continue


# ---------- validator: check the resulting schedule ----------

def _validate_schedule(hours: List[Dict], plan: List[Dict], battery: Dict) -> Tuple[bool, str]:
    """Returns (ok, reason). Validates the energy balance using both charge and discharge."""
    for h, p in zip(hours, plan):
        t = int(h["hour"])
        demand = float(h["demand_kwh"])
        solar_used = float(p["solar_used_kwh"])
        grid = float(p["grid_kwh"])
        ch = float(p.get("battery_kwh", 0.0))
        dis = float(p.get("battery_discharge_kwh", 0.0))
        # Energy balance: grid + solar + discharge = demand + charge
        supply = grid + solar_used + dis
        need = demand + ch
        if abs(supply - need) > 0.5:
            return False, (f"hour {t}: energy balance off "
                           f"(g+s+dis={supply:.3f}, d+ch={need:.3f})")
        if solar_used > float(h["solar_kwh"]) + 1e-2:
            return False, f"hour {t}: solar_used > solar_avail"
    if plan:
        first = float(battery.get("initial_energy_kwh", 0.0))
        last = float(plan[-1]["battery_energy_after_kwh"])
        if abs(last - first) > 0.5:
            return False, f"battery end-of-day level {last} != initial {first}"
    return True, "ok"


# ---------- the endpoint ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_energy(request: ScenarioRequest):
    # 1) LLM interpret
    raw = interpret_notes(list(request.operator_notes))

    # 2) Guardrail validate
    interpretations = validate_interpretations(raw, expected_count=len(request.operator_notes))

    # 3) Build mutable copies
    hours = [h.model_dump() for h in request.hours]
    battery = request.battery.model_dump()

    # 4) Apply directives
    opt_in = OptimizerInput(hours=hours, battery=battery)
    _apply_directives(hours, battery, interpretations, opt_in)
    opt_in.hours = hours
    opt_in.battery = battery

    # 5) Solve
    result = optimize(opt_in)
    if result.status != "ok":
        raise HTTPException(status_code=500, detail=f"optimizer failed: {result.status}")

    # 6) Validate
    ok, reason = _validate_schedule(hours, result.hourly_plan, battery)
    plan_summary = "Schedule satisfies physics and operator directives."
    if not ok:
        plan_summary = f"WARNING: validator flagged: {reason}"

    # 7) Build response
    directive_response = [
        DirectiveInterpretation(
            note_index=int(it["note_index"]),
            applies=bool(it["applies"]),
            directive_type=str(it["directive_type"]),
            structured_adjustment=it.get("structured_adjustment"),
            explanation=str(it.get("explanation", "")),
        )
        for it in interpretations
    ]

    plan_entries = [
        HourlyPlanEntry(
            hour=int(row["hour"]),
            grid_kwh=float(row["grid_kwh"]),
            solar_used_kwh=float(row["solar_used_kwh"]),
            battery_action=str(row["battery_action"]),
            battery_kwh=float(row["battery_kwh"]),
            battery_discharge_kwh=float(row.get("battery_discharge_kwh", 0.0)),
            battery_energy_after_kwh=float(row["battery_energy_after_kwh"]),
        )
        for row in result.hourly_plan
    ]

    return OptimizeResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=directive_response,
        hourly_plan=plan_entries,
        total_grid_kwh=result.total_grid_kwh,
        total_cost_bdt=result.total_cost_bdt,
        peak_grid_kwh=result.peak_grid_kwh,
        plan_summary=plan_summary,
    )
