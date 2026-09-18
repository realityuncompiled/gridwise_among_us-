from fastapi import FastAPI
from app.models import EnergyScenario

app = FastAPI(title="GridWise Energy Optimization API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-energy")
def optimize_energy(scenario: EnergyScenario):
    return {
        "scenario_id": scenario.scenario_id,
        "message": "Scenario received successfully"
    }