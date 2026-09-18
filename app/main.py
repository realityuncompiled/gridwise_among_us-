from fastapi import FastAPI, HTTPException, status
from app.models import (
    HealthResponse,
    OptimizeEnergyRequest,
    OptimizeEnergyResponse
)
from app.llm import interpret_operator_notes
from app.directives import validate_and_sanitize_directives
from app.optimizer import generate_plan

app = FastAPI(title="GridWise API", version="1.0.0")

@app.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def health_check():
    return HealthResponse(status="ok")

@app.post("/optimize-energy", response_model=OptimizeEnergyResponse, status_code=status.HTTP_200_OK)
def optimize_energy(request: OptimizeEnergyRequest):
    try:
        # 1. Interpret notes via LLM
        raw_interpretations = interpret_operator_notes(request.operator_notes)
        
        # 2. Validate extracted directives via Guardrails
        validated_directives = validate_and_sanitize_directives(
            raw_interpretations,
            len(request.operator_notes),
            request.battery
        )
        
        # 3. Generate 24-hour schedule
        plan, total_grid, total_cost, peak_grid = generate_plan(request, validated_directives)
        
        return OptimizeEnergyResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=validated_directives,
            hourly_plan=plan,
            total_grid_kwh=total_grid,
            total_cost_bdt=total_cost,
            peak_grid_kwh=peak_grid,
            plan_summary="Sprint 1 heuristic baseline schedule generated successfully."
        )

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal operational error")