from typing import List, Dict
from app.models import HourData, BatteryConfig

def run_optimization(hours: List[HourData], battery: BatteryConfig, directives: List[Dict]):
    # This will be replaced later with the actual mathematical optimization code from teammate #3.
    # For now, it generates a 24-hour dummy plan to keep the pipeline functional.
    hourly_plan = []
    
    for h in hours:
        hourly_plan.append({
            "hour": h.hour,
            "grid_kwh": round(h.demand_kwh * 0.8, 2),
            "solar_used_kwh": round(min(h.solar_kwh, h.demand_kwh * 0.2), 2),
            "battery_action": "hold",
            "battery_kwh": 0.0,
            "battery_energy_after_kwh": battery.initial_energy_kwh
        })
        
    return {
        "hourly_plan": hourly_plan,
        "total_grid_kwh": round(sum(p["grid_kwh"] for p in hourly_plan), 2),
        "total_cost_bdt": round(sum(p["grid_kwh"] * h.tariff_bdt_per_kwh for p, h in zip(hourly_plan, hours)), 2),
        "peak_grid_kwh": max(p["grid_kwh"] for p in hourly_plan),
        "plan_summary": "Mock optimization generated successfully based on current directives."
    }
    # This will be replaced later with the actual mathematical optimization code from teammate #3.
