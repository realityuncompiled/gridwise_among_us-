"""
Mathematical Energy Optimizer for Smart Campus Energy Optimization Challenge.
Solves the 24-hour cost minimization problem via Linear Programming using SciPy HiGHS.
Strictly implements Problem Statement Sections 05.2, 05.3, and 09.
"""

import numpy as np
from scipy.optimize import linprog
from typing import Dict, List, Tuple
from schemas import (
    OptimizeRequest,
    DirectiveInterpretationEntry,
    HourlyPlanEntry
)


def solve_energy_optimization(
    request: OptimizeRequest,
    directives: List[DirectiveInterpretationEntry]
) -> List[HourlyPlanEntry]:
    """
    Formulates and solves the 24-hour Linear Program (LP):
    Variables for each hour h in 0..23 (total 5 * 24 = 120 variables):
      g_h: grid import (kWh)
      s_h: solar used (kWh)
      c_h: battery charge (kWh)
      d_h: battery discharge (kWh)
      E_h: battery state of charge at end of hour h (kWh)
    """
    T = 24
    battery = request.battery
    hours_data = request.hours

    # 1. Base arrays
    demand = np.array([h.demand_kwh for h in hours_data], dtype=float)
    base_solar = np.array([h.solar_kwh for h in hours_data], dtype=float)
    tariffs = np.array([h.tariff_bdt_per_kwh for h in hours_data], dtype=float)

    # Effective parameters modified by directives
    effective_solar = base_solar.copy()
    min_reserve = np.full(T, battery.minimum_energy_kwh, dtype=float)
    max_charge = np.full(T, battery.max_charge_kwh_per_hour, dtype=float)
    max_discharge = np.full(T, battery.max_discharge_kwh_per_hour, dtype=float)
    max_grid = np.full(T, np.inf, dtype=float)

    # 2. Apply validated directives
    for d in directives:
        if not d.applies or not d.structured_adjustment:
            continue
        adj = d.structured_adjustment
        affected_hours = adj.get("hours", [])

        if d.directive_type == "solar_reduction":
            factor = float(adj.get("factor", 1.0))
            for h in affected_hours:
                if 0 <= h < T:
                    effective_solar[h] = min(effective_solar[h], base_solar[h] * factor)

        elif d.directive_type == "minimum_battery_reserve":
            req_reserve = float(adj.get("minimum_energy_kwh", battery.minimum_energy_kwh))
            for h in affected_hours:
                if 0 <= h < T:
                    min_reserve[h] = max(min_reserve[h], req_reserve)

        elif d.directive_type == "no_charge_window":
            for h in affected_hours:
                if 0 <= h < T:
                    max_charge[h] = 0.0

        elif d.directive_type == "no_discharge_window":
            for h in affected_hours:
                if 0 <= h < T:
                    max_discharge[h] = 0.0

        elif d.directive_type == "max_grid_window":
            cap = float(adj.get("max_grid_kwh", np.inf))
            for h in affected_hours:
                if 0 <= h < T:
                    max_grid[h] = min(max_grid[h], cap)

    # 3. Variable indices in vector x:
    # x = [g_0..g_23, s_0..s_23, c_0..c_23, d_0..d_23, E_0..E_23]
    IDX_G = 0
    IDX_S = T
    IDX_C = 2 * T
    IDX_D = 3 * T
    IDX_E = 4 * T
    num_vars = 5 * T

    # 4. Objective vector: minimize sum(g_h * tariff_h)
    # Slight tie-breaker epsilon on solar (-1e-6 * s) and cycling (+1e-7 * (c + d))
    c_obj = np.zeros(num_vars)
    for h in range(T):
        c_obj[IDX_G + h] = tariffs[h]
        c_obj[IDX_S + h] = -1e-6  # Prefer free solar
        c_obj[IDX_C + h] = 1e-7   # Avoid unnecessary battery wear
        c_obj[IDX_D + h] = 1e-7

    # 5. Variable bounds
    bounds = []
    # g_h: [0, max_grid[h]]
    for h in range(T):
        ub = max_grid[h] if np.isfinite(max_grid[h]) else None
        bounds.append((0.0, ub))
    # s_h: [0, effective_solar[h]]
    for h in range(T):
        bounds.append((0.0, float(effective_solar[h])))
    # c_h: [0, max_charge[h]]
    for h in range(T):
        bounds.append((0.0, float(max_charge[h])))
    # d_h: [0, max_discharge[h]]
    for h in range(T):
        bounds.append((0.0, float(max_discharge[h])))
    # E_h: [min_reserve[h], capacity_kwh]
    for h in range(T):
        bounds.append((float(min_reserve[h]), float(battery.capacity_kwh)))

    # 6. Equality Constraints: A_eq * x = b_eq
    A_eq_rows = []
    b_eq_rows = []

    # Constraint 1: Hourly Energy Balance (24 equations)
    # g_h + s_h + d_h - c_h = demand[h]
    for h in range(T):
        row = np.zeros(num_vars)
        row[IDX_G + h] = 1.0
        row[IDX_S + h] = 1.0
        row[IDX_D + h] = 1.0
        row[IDX_C + h] = -1.0
        A_eq_rows.append(row)
        b_eq_rows.append(demand[h])

    # Constraint 2: Battery State Dynamics (24 equations)
    # Hour 0: E_0 - c_0 + d_0 = initial_energy_kwh
    row0 = np.zeros(num_vars)
    row0[IDX_E + 0] = 1.0
    row0[IDX_C + 0] = -1.0
    row0[IDX_D + 0] = 1.0
    A_eq_rows.append(row0)
    b_eq_rows.append(battery.initial_energy_kwh)

    # Hours 1..23: E_h - E_{h-1} - c_h + d_h = 0
    for h in range(1, T):
        row = np.zeros(num_vars)
        row[IDX_E + h] = 1.0
        row[IDX_E + (h - 1)] = -1.0
        row[IDX_C + h] = -1.0
        row[IDX_D + h] = 1.0
        A_eq_rows.append(row)
        b_eq_rows.append(0.0)

    # Constraint 3: End-of-Day Neutrality (1 equation)
    # E_23 = initial_energy_kwh
    row_end = np.zeros(num_vars)
    row_end[IDX_E + (T - 1)] = 1.0
    A_eq_rows.append(row_end)
    b_eq_rows.append(battery.initial_energy_kwh)

    A_eq = np.array(A_eq_rows, dtype=float)
    b_eq = np.array(b_eq_rows, dtype=float)

    # 7. Solve with HiGHS LP Solver
    res = linprog(
        c=c_obj,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs"
    )

    if not res.success:
        raise ValueError(f"Energy optimization failed: {res.message}")

    x = res.x
    g_raw = x[IDX_G : IDX_G + T]
    s_raw = x[IDX_S : IDX_S + T]
    c_raw = x[IDX_C : IDX_C + T]
    d_raw = x[IDX_D : IDX_D + T]
    E_raw = x[IDX_E : IDX_E + T]

    # 8. Clean and Discretize Battery Actions & Guarantee Invariants
    hourly_plan: List[HourlyPlanEntry] = []
    current_energy = battery.initial_energy_kwh

    for h in range(T):
        g_val = max(0.0, float(g_raw[h]))
        s_val = max(0.0, min(float(s_raw[h]), float(effective_solar[h])))
        c_val = max(0.0, float(c_raw[h]))
        d_val = max(0.0, float(d_raw[h]))

        # Cancel any simultaneous charge and discharge
        if c_val > 1e-6 and d_val > 1e-6:
            cancel_amt = min(c_val, d_val)
            c_val -= cancel_amt
            d_val -= cancel_amt

        # Action assignment
        if c_val > 1e-5:
            action = "charge"
            kwh = c_val
            current_energy += kwh
        elif d_val > 1e-5:
            action = "discharge"
            kwh = d_val
            current_energy -= kwh
        else:
            action = "idle"
            kwh = 0.0

        # Adjust grid_kwh to maintain exact energy balance:
        # grid_kwh + solar_used_kwh + discharge_kwh = demand_kwh + charge_kwh
        # grid_kwh = demand_kwh + (charge_kwh if action=='charge' else 0) - solar_used_kwh - (discharge_kwh if action=='discharge' else 0)
        net_battery_flow = kwh if action == "charge" else (-kwh if action == "discharge" else 0.0)
        required_grid = demand[h] + net_battery_flow - s_val
        g_val = max(0.0, float(required_grid))

        entry = HourlyPlanEntry(
            hour=h,
            grid_kwh=round(g_val, 4),
            solar_used_kwh=round(s_val, 4),
            battery_action=action,
            battery_kwh=round(kwh, 4),
            battery_energy_after_kwh=round(current_energy, 4)
        )
        hourly_plan.append(entry)

    # Force exact neutrality on hour 23 if floating-point drift occurred
    if abs(hourly_plan[-1].battery_energy_after_kwh - battery.initial_energy_kwh) < 0.01:
        hourly_plan[-1].battery_energy_after_kwh = battery.initial_energy_kwh

    return hourly_plan
