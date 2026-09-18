"""
Replay Validator and Schedule Verification for Smart Campus Energy Optimization Challenge.
Independently verifies all physical, operational, and directive constraints (Section 09, 11).
Recalculates exact totals: total_grid_kwh, total_cost_bdt, peak_grid_kwh.
"""

from typing import Dict, List, Tuple
from schemas import (
    OptimizeRequest,
    DirectiveInterpretationEntry,
    HourlyPlanEntry
)


def verify_and_recalculate_schedule(
    request: OptimizeRequest,
    directives: List[DirectiveInterpretationEntry],
    hourly_plan: List[HourlyPlanEntry]
) -> Tuple[float, float, float, str]:
    """
    Independently audits the 24-hour hourly_plan against:
    - Hourly energy balance
    - Effective solar limits (including solar_reduction directives)
    - Battery capacity and reserve bounds (including minimum_battery_reserve directives)
    - Hourly charge/discharge rate limits
    - Directive windows (no_charge_window, no_discharge_window, max_grid_window)
    - End-of-day battery neutrality
    
    Returns:
        total_grid_kwh, total_cost_bdt, peak_grid_kwh, plan_summary
    """
    T = 24
    battery = request.battery
    hours_data = request.hours
    
    # Pre-calculate effective limits modified by directives
    effective_solar = [h.solar_kwh for h in hours_data]
    min_reserve = [battery.minimum_energy_kwh] * T
    no_charge_hours = set()
    no_discharge_hours = set()
    max_grid_caps: Dict[int, float] = {}

    for d in directives:
        if not d.applies or not d.structured_adjustment:
            continue
        adj = d.structured_adjustment
        aff_hours = adj.get("hours", [])

        if d.directive_type == "solar_reduction":
            factor = float(adj.get("factor", 1.0))
            for h in aff_hours:
                if 0 <= h < T:
                    effective_solar[h] = min(effective_solar[h], hours_data[h].solar_kwh * factor)

        elif d.directive_type == "minimum_battery_reserve":
            req_res = float(adj.get("minimum_energy_kwh", battery.minimum_energy_kwh))
            for h in aff_hours:
                if 0 <= h < T:
                    min_reserve[h] = max(min_reserve[h], req_res)

        elif d.directive_type == "no_charge_window":
            for h in aff_hours:
                no_charge_hours.add(h)

        elif d.directive_type == "no_discharge_window":
            for h in aff_hours:
                no_discharge_hours.add(h)

        elif d.directive_type == "max_grid_window":
            cap = float(adj.get("max_grid_kwh", float("inf")))
            for h in aff_hours:
                max_grid_caps[h] = min(max_grid_caps.get(h, float("inf")), cap)

    # Replay simulation
    current_energy = battery.initial_energy_kwh
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for h, plan_entry in enumerate(hourly_plan):
        hour_data = hours_data[h]
        grid = plan_entry.grid_kwh
        solar_used = plan_entry.solar_used_kwh
        action = plan_entry.battery_action
        bat_kwh = plan_entry.battery_kwh

        # Accumulate metrics
        total_grid += grid
        total_cost += grid * hour_data.tariff_bdt_per_kwh
        if grid > peak_grid:
            peak_grid = grid

        # 1. Non-negative checks
        if grid < -0.01 or solar_used < -0.01 or bat_kwh < -0.01:
            raise ValueError(f"Hour {h}: Negative energy values encountered.")

        # 2. Solar usage check
        if solar_used > effective_solar[h] + 0.05:
            raise ValueError(f"Hour {h}: Solar used ({solar_used}) exceeds effective solar ({effective_solar[h]}).")

        # 3. Directive window checks
        if h in no_charge_hours and action == "charge" and bat_kwh > 0.01:
            raise ValueError(f"Hour {h}: Charged battery during no_charge_window.")

        if h in no_discharge_hours and action == "discharge" and bat_kwh > 0.01:
            raise ValueError(f"Hour {h}: Discharged battery during no_discharge_window.")

        if h in max_grid_caps and grid > max_grid_caps[h] + 0.05:
            raise ValueError(f"Hour {h}: Grid import ({grid}) exceeds max_grid_window cap ({max_grid_caps[h]}).")

        # 4. Battery action and state transition check
        if action == "charge":
            if bat_kwh > battery.max_charge_kwh_per_hour + 0.05:
                raise ValueError(f"Hour {h}: Charge {bat_kwh} exceeds max rate {battery.max_charge_kwh_per_hour}.")
            current_energy += bat_kwh
            supplied = grid + solar_used
            required = hour_data.demand_kwh + bat_kwh
        elif action == "discharge":
            if bat_kwh > battery.max_discharge_kwh_per_hour + 0.05:
                raise ValueError(f"Hour {h}: Discharge {bat_kwh} exceeds max rate {battery.max_discharge_kwh_per_hour}.")
            current_energy -= bat_kwh
            supplied = grid + solar_used + bat_kwh
            required = hour_data.demand_kwh
        else:
            if bat_kwh > 0.01:
                raise ValueError(f"Hour {h}: Battery action is idle but battery_kwh is {bat_kwh}.")
            supplied = grid + solar_used
            required = hour_data.demand_kwh

        # 5. Energy balance check: supplied == required
        if abs(supplied - required) > 0.1:
            raise ValueError(f"Hour {h}: Energy balance violation: supplied {supplied:.2f} != required {required:.2f}.")

        # 6. Battery bounds check
        if current_energy < min_reserve[h] - 0.05:
            raise ValueError(f"Hour {h}: Battery energy {current_energy:.2f} falls below required reserve {min_reserve[h]:.2f}.")
        if current_energy > battery.capacity_kwh + 0.05:
            raise ValueError(f"Hour {h}: Battery energy {current_energy:.2f} exceeds capacity {battery.capacity_kwh:.2f}.")

    # 7. End-of-day neutrality check
    if abs(current_energy - battery.initial_energy_kwh) > 0.1:
        raise ValueError(
            f"End-of-day battery neutrality violation: final energy {current_energy:.2f} != initial {battery.initial_energy_kwh:.2f}"
        )

    # 8. Generate concise plan summary
    charged_count = sum(1 for p in hourly_plan if p.battery_action == "charge")
    discharged_count = sum(1 for p in hourly_plan if p.battery_action == "discharge")
    active_directives = [d.directive_type for d in directives if d.applies]
    summary_parts = [
        f"Generated valid 24-hour optimal schedule satisfying all operational and battery neutrality constraints.",
        f"Total grid import: {round(total_grid, 2)} kWh at a total cost of {round(total_cost, 2)} BDT with peak import {round(peak_grid, 2)} kWh.",
        f"Battery was charged in {charged_count} hours and discharged in {discharged_count} hours to avoid high tariff periods.",
    ]
    if active_directives:
        summary_parts.append(f"Successfully satisfied {len(active_directives)} operator directive(s): {', '.join(set(active_directives))}.")
    else:
        summary_parts.append("No operative directives were required for this scenario.")

    plan_summary = " ".join(summary_parts)

    return round(total_grid, 2), round(total_cost, 2), round(peak_grid, 2), plan_summary
