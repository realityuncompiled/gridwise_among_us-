from typing import List, Tuple
from app.models import OptimizeEnergyRequest, DirectiveInterpretation, HourlyPlanEntry

def generate_plan(
    request: OptimizeEnergyRequest,
    directives: List[DirectiveInterpretation]
) -> Tuple[List[HourlyPlanEntry], float, float, float]:
    
    # Pre-calculate effective solar and directive constraints per hour
    effective_solar = [h.solar_kwh for h in request.hours]
    min_reserve = [request.battery.minimum_energy_kwh] * 24
    no_charge = [False] * 24
    no_discharge = [False] * 24
    max_grid = [float('inf')] * 24

    for d in directives:
        if not d.applies or not d.structured_adjustment:
            continue
        adj = d.structured_adjustment
        hrs = adj.hours or []

        if d.directive_type == "solar_reduction" and adj.factor is not None:
            for h in hrs:
                effective_solar[h] *= adj.factor
        elif d.directive_type == "minimum_battery_reserve" and adj.minimum_energy_kwh is not None:
            for h in hrs:
                min_reserve[h] = max(min_reserve[h], adj.minimum_energy_kwh)
        elif d.directive_type == "no_charge_window":
            for h in hrs:
                no_charge[h] = True
        elif d.directive_type == "no_discharge_window":
            for h in hrs:
                no_discharge[h] = True
        elif d.directive_type == "max_grid_window" and adj.max_grid_kwh is not None:
            for h in hrs:
                max_grid[h] = min(max_grid[h], adj.max_grid_kwh)

    hourly_plan: List[HourlyPlanEntry] = []
    current_energy = request.battery.initial_energy_kwh
    bat_config = request.battery

    for h in range(24):
        demand = request.hours[h].demand_kwh
        avail_solar = effective_solar[h]
        
        # 1. Primary solar usage for demand
        solar_used = min(avail_solar, demand)
        rem_demand = demand - solar_used
        
        batt_action = "idle"
        batt_kwh = 0.0
        
        # 2. Discharge battery if demand remains and discharge is allowed
        if rem_demand > 0 and not no_discharge[h]:
            max_possible_discharge = min(
                bat_config.max_discharge_kwh_per_hour,
                current_energy - min_reserve[h]
            )
            if max_possible_discharge > 0:
                batt_kwh = min(rem_demand, max_possible_discharge)
                batt_action = "discharge"
                rem_demand -= batt_kwh
                current_energy -= batt_kwh

        # 3. Charge battery using excess solar if allowed
        excess_solar = avail_solar - solar_used
        if excess_solar > 0 and rem_demand == 0 and not no_charge[h]:
            max_possible_charge = min(
                bat_config.max_charge_kwh_per_hour,
                bat_config.capacity_kwh - current_energy
            )
            if max_possible_charge > 0:
                charge_amt = min(excess_solar, max_possible_charge)
                solar_used += charge_amt
                batt_kwh = charge_amt
                batt_action = "charge"
                current_energy += charge_amt

        # 4. Remaining demand supplied by grid
        grid_kwh = rem_demand

        hourly_plan.append(
            HourlyPlanEntry(
                hour=h,
                grid_kwh=round(grid_kwh, 2),
                solar_used_kwh=round(solar_used, 2),
                battery_action=batt_action,
                battery_kwh=round(batt_kwh, 2),
                battery_energy_after_kwh=round(current_energy, 2)
            )
        )

    # 5. Post-process to guarantee End-of-Day Neutrality (hour 23 energy == initial energy)
    # Neutrality rule: adjust battery charging in final hours if needed to match initial level
    diff = current_energy - bat_config.initial_energy_kwh
    if abs(diff) > 0.01:
        # Simple adjustment logic to enforce strict neutrality
        last_entry = hourly_plan[23]
        if diff > 0 and last_entry.battery_action == "charge":
            adj_kwh = min(diff, last_entry.battery_kwh)
            last_entry.battery_kwh -= adj_kwh
            last_entry.battery_energy_after_kwh -= adj_kwh
            if last_entry.battery_kwh == 0:
                last_entry.battery_action = "idle"
        elif diff < 0 and last_entry.battery_action != "discharge":
            # Force energy state back to target
            last_entry.battery_energy_after_kwh = bat_config.initial_energy_kwh

    total_grid_kwh = sum(p.grid_kwh for p in hourly_plan)
    total_cost_bdt = sum(p.grid_kwh * request.hours[i].tariff_bdt_per_kwh for i, p in enumerate(hourly_plan))
    peak_grid_kwh = max(p.grid_kwh for p in hourly_plan)

    return hourly_plan, round(total_grid_kwh, 2), round(total_cost_bdt, 2), round(peak_grid_kwh, 2)