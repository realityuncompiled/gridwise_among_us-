from fastapi import FastAPI
from app.models import EnergyScenario, OptimizationResponse

app = FastAPI(title="GridWise Energy Optimization API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizationResponse)
def optimize_energy(scenario: EnergyScenario):
    return {
        "scenario_id": scenario.scenario_id,
        "directive_interpretation": [],
        "hourly_plan": [],
        "total_grid_kwh": 0,
        "total_cost_bdt": 0,
        "peak_grid_kwh": 0,
        "plan_summary": "Optimization not implemented yet"
    }