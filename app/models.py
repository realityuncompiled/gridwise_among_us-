from pydantic import BaseModel, Field
from typing import List


class HourData(BaseModel):
    hour: int
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float


class BatteryConfig(BaseModel):
    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float


class EnergyScenario(BaseModel):
    scenario_id: str
    operator_notes: List[str] = Field(min_length=1, max_length=3)
    hours: List[HourData]
    battery: BatteryConfig