from fastapi import FastAPI
from app.models import EnergyScenario, OptimizationResponse
from app.llm import interpret_and_validate_notes
from app.optimizer import run_optimization  # 👈 Importing the optimizer

app = FastAPI(title="GridWise Energy Optimization API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizationResponse)
def optimize_energy(scenario: EnergyScenario):
    # 1. Call Teammate 2's LLM part
    directives = interpret_and_validate_notes(
        scenario.operator_notes,
        battery_capacity_kwh=scenario.battery.capacity_kwh,
    )
    
    # 2. Call Teammate 3's Optimizer part
    optimization_result = run_optimization(
        hours=scenario.hours,
        battery=scenario.battery,
        directives=directives
    )
    
    # 3. Return the fully validated response
    return {
        "scenario_id": scenario.scenario_id,
        "directive_interpretation": directives,
        "hourly_plan": optimization_result["hourly_plan"],
        "total_grid_kwh": optimization_result["total_grid_kwh"],
        "total_cost_bdt": optimization_result["total_cost_bdt"],
        "peak_grid_kwh": optimization_result["peak_grid_kwh"],
        "plan_summary": optimization_result["plan_summary"]
    }
