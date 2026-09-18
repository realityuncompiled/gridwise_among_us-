from pydantic import BaseModel
from typing import List, Optional


# ---------- REQUEST MODELS ----------

class HourData(BaseModel):
    hour: int
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float


class Battery(BaseModel):
    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float


class ScenarioRequest(BaseModel):
    scenario_id: str
    operator_notes: List[str]
    hours: List[HourData]
    battery: Battery


# ---------- RESPONSE MODELS ----------

class DirectiveInterpretation(BaseModel):
    note_index: int
    applies: bool
    directive_type: str
    structured_adjustment: Optional[dict] = None
    explanation: str


class HourlyPlanEntry(BaseModel):
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: str
    battery_kwh: float             # legacy field: amount of energy moved INTO the battery this hour
    battery_discharge_kwh: float = 0.0  # amount drawn out this hour (new field)
    battery_energy_after_kwh: float


class OptimizeResponse(BaseModel):
    scenario_id: str
    directive_interpretation: List[DirectiveInterpretation]
    hourly_plan: List[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str