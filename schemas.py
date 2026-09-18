"""
Pydantic schemas for Smart Campus Energy Optimization Challenge.
Strictly conforms to Problem Statement Sections 06, 07, and 10.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request Schemas (Section 07)
# ---------------------------------------------------------------------------

class HourEntry(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Unique integer from 0 to 23.")
    demand_kwh: float = Field(..., ge=0, description="Campus demand that must be supplied in this hour.")
    solar_kwh: float = Field(..., ge=0, description="Base solar energy available before adjustments.")
    tariff_bdt_per_kwh: float = Field(..., ge=0, description="Grid electricity price for this hour.")


class BatteryConfig(BaseModel):
    capacity_kwh: float = Field(..., gt=0, description="Maximum energy the battery can store.")
    initial_energy_kwh: float = Field(..., ge=0, description="Battery energy at start of hour 0.")
    minimum_energy_kwh: float = Field(..., ge=0, description="Base reserve level the battery must never go below.")
    max_charge_kwh_per_hour: float = Field(..., ge=0, description="Maximum energy that may be added in one hour.")
    max_discharge_kwh_per_hour: float = Field(..., ge=0, description="Maximum energy that may be removed in one hour.")

    @field_validator("initial_energy_kwh")
    @classmethod
    def validate_initial_energy(cls, v: float, info) -> float:
        capacity = info.data.get("capacity_kwh")
        if capacity is not None and v > capacity:
            raise ValueError(f"initial_energy_kwh ({v}) cannot exceed capacity_kwh ({capacity})")
        return v

    @field_validator("minimum_energy_kwh")
    @classmethod
    def validate_minimum_energy(cls, v: float, info) -> float:
        capacity = info.data.get("capacity_kwh")
        if capacity is not None and v > capacity:
            raise ValueError(f"minimum_energy_kwh ({v}) cannot exceed capacity_kwh ({capacity})")
        return v


class OptimizeRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1, description="Unique synthetic scenario identifier.")
    operator_notes: List[str] = Field(..., min_length=1, max_length=3, description="1 to 3 natural-language notes.")
    hours: List[HourEntry] = Field(..., min_length=24, max_length=24, description="Hourly entries for hours 0..23.")
    battery: BatteryConfig = Field(..., description="Battery parameters.")

    @field_validator("hours")
    @classmethod
    def validate_hours_sequence(cls, v: List[HourEntry]) -> List[HourEntry]:
        if len(v) != 24:
            raise ValueError(f"hours array must contain exactly 24 entries, got {len(v)}")
        hours_list = [entry.hour for entry in v]
        if set(hours_list) != set(range(24)):
            raise ValueError(f"hours array must contain unique hours from 0 to 23")
        return v


# ---------------------------------------------------------------------------
# Directive Interpretation Schemas (Section 04 & 10.2)
# ---------------------------------------------------------------------------

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op"
]

BatteryAction = Literal["charge", "discharge", "idle"]


class DirectiveInterpretationEntry(BaseModel):
    note_index: int = Field(..., ge=0, description="Zero-based index of corresponding operator note.")
    applies: bool = Field(..., description="true for applicable non-no_op directives; false only for no_op.")
    directive_type: DirectiveType = Field(..., description="One supported directive type.")
    structured_adjustment: Optional[Dict[str, Any]] = Field(None, description="Structured adjustment object, or null only for no_op.")
    explanation: str = Field(..., description="Short explanation of the interpretation.")


# ---------------------------------------------------------------------------
# Hourly Plan & Response Schemas (Section 10)
# ---------------------------------------------------------------------------

class HourlyPlanEntry(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Hour 0 through 23.")
    grid_kwh: float = Field(..., ge=0, description="Non-negative grid energy purchased.")
    solar_used_kwh: float = Field(..., ge=0, description="Solar energy used; <= effective solar.")
    battery_action: BatteryAction = Field(..., description="Exactly one of: charge, discharge, idle.")
    battery_kwh: float = Field(..., ge=0, description="Non-negative magnitude; 0 when idle.")
    battery_energy_after_kwh: float = Field(..., ge=0, description="Battery energy immediately after hour.")


class OptimizeResponse(BaseModel):
    scenario_id: str = Field(..., description="Must match request scenario_id.")
    directive_interpretation: List[DirectiveInterpretationEntry] = Field(..., description="Interpretation for every note in note_index order.")
    hourly_plan: List[HourlyPlanEntry] = Field(..., min_length=24, max_length=24, description="Hourly plan for hours 0..23.")
    total_grid_kwh: float = Field(..., ge=0, description="Sum of grid_kwh across all 24 hours.")
    total_cost_bdt: float = Field(..., ge=0, description="Calculated total grid electricity cost.")
    peak_grid_kwh: float = Field(..., ge=0, description="Maximum hourly grid_kwh in plan.")
    plan_summary: str = Field(..., description="Short human-readable explanation of strategy.")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
