"""
FastAPI application for Smart Campus Energy Optimization Challenge.
Provides GET /health and POST /optimize-energy endpoints according to Problem Statement Section 06.
"""

import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from schemas import (
    OptimizeRequest,
    OptimizeResponse,
    HealthResponse
)
from interpreter import interpret_operator_notes_llm
from guardrails import validate_and_guard_directives
from optimizer import solve_energy_optimization
from verifier import verify_and_recalculate_schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main_api")

app = FastAPI(
    title="Smart Campus Energy Optimization API",
    description="LLM-Assisted Operator Directive Interpretation & 24-Hour Energy Scheduling",
    version="1.0.0"
)


# ---------------------------------------------------------------------------
# Error Handlers for Clean & Safe Responses (Section 06.1)
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Request validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Malformed JSON or structurally invalid request.", "errors": exc.errors()}
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    logger.warning(f"Pydantic validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Malformed JSON or structurally invalid request.", "errors": exc.errors()}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Controlled server error on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Controlled internal error processing energy optimization."}
    )


# ---------------------------------------------------------------------------
# API Endpoints (Section 06)
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    """Readiness endpoint for judging harness. Returns status = 'ok'."""
    return HealthResponse(status="ok")


@app.post("/optimize-energy", response_model=OptimizeResponse, status_code=status.HTTP_200_OK)
async def optimize_energy(request: OptimizeRequest):
    """
    Accepts 24-hour scenario with operator notes.
    Performs LLM interpretation, deterministic guardrailing, LP optimization,
    schedule verification, and returns the machine-checkable plan.
    """
    logger.info(f"Received optimization request for scenario_id: {request.scenario_id}")

    # Step 1: Interpret operator notes using language model
    raw_directives = await interpret_operator_notes_llm(
        request.operator_notes,
        request.battery
    )

    # Step 2: Deterministic Guardrails
    guarded_directives = validate_and_guard_directives(
        raw_directives,
        request.operator_notes,
        request.battery
    )

    # Step 3: Mathematical Energy Optimization (HiGHS LP)
    hourly_plan = solve_energy_optimization(
        request,
        guarded_directives
    )

    # Step 4: Schedule Replay & Exact Recalculation
    total_grid, total_cost, peak_grid, plan_summary = verify_and_recalculate_schedule(
        request,
        guarded_directives,
        hourly_plan
    )

    # Step 5: Construct Final Response
    response = OptimizeResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=guarded_directives,
        hourly_plan=hourly_plan,
        total_grid_kwh=total_grid,
        total_cost_bdt=total_cost,
        peak_grid_kwh=peak_grid,
        plan_summary=plan_summary
    )

    logger.info(f"Scenario {request.scenario_id} successfully scheduled. Total Cost: {total_cost} BDT")
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
