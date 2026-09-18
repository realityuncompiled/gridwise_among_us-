from pydantic import BaseModel, Field, field_validator
from typing import List,  Optional
class HourData(BaseModel):
    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0)
    solar_kwh: float = Field(ge=0)
    tariff_bdt_per_kwh: float = Field(ge=0)


class BatteryConfig(BaseModel):
    capacity_kwh: float = Field(ge=0)
    initial_energy_kwh: float = Field(ge=0)
    minimum_energy_kwh: float = Field(ge=0)
    max_charge_kwh_per_hour: float = Field(ge=0)
    max_discharge_kwh_per_hour: float = Field(ge=0)


class EnergyScenario(BaseModel):
    scenario_id: str
    operator_notes: List[str] = Field(min_length=1, max_length=3)
    hours: List[HourData] = Field(min_length=24, max_length=24)
    battery: BatteryConfig

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, value):
        hour_numbers = [item.hour for item in value]

        if hour_numbers != list(range(24)):
            raise ValueError("hours must contain exactly 0 through 23 in order")

        return value
class DirectiveInterpretation(BaseModel):
    note_index: int
    original_note: str
    directive_type: str
    parameters: Optional[dict] = None 
    applies: bool
    confidence: float


class HourlyPlan(BaseModel):
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: str
    battery_kwh: float
    battery_energy_after_kwh: float


class OptimizationResponse(BaseModel):
    scenario_id: str
    directive_interpretation: List[DirectiveInterpretation]
    hourly_plan: List[HourlyPlan]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str