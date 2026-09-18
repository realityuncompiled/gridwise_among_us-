from fastapi import FastAPI
from app.models import EnergyScenario, OptimizationResponse
from app.llm import interpret_and_validate_notes  

app = FastAPI(title="GridWise Energy Optimization API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizationResponse)
def optimize_energy(scenario: EnergyScenario):
    
    directives = interpret_and_validate_notes(
        scenario.operator_notes,
        battery_capacity_kwh=scenario.battery.capacity_kwh,
    )
    
    
    return {
        "scenario_id": scenario.scenario_id,
        "directive_interpretation": directives,
        "hourly_plan": [],  
        "total_grid_kwh": 0,
        "total_cost_bdt": 0,
        "peak_grid_kwh": 0,
        "plan_summary": "LLM integrated successfully. Waiting for optimizer module."
    }
