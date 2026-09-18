"""
optimizer.py
------------
24 ghonta-r LP (linear programming) solver.

Decision variables (5-ti vector, each of length T=24):
    g[t]       : grid theke koto kWh kinechi (hour t-te)
    s[t]       : solar theke koto kWh actually use korechi  (0 <= s[t] <= solar_kwh[t])
    b_ch[t]    : battery koto kWh charge korechi
    b_dis[t]   : battery theke koto kWh discharge korechi
    b_level[t] : battery-te shesh energy (kWh) hour t-r sheshe

Constraints:
    - Energy balance: g[t] + s[t] + b_dis[t] == demand[t] + b_ch[t]
    - Solar limit:    0 <= s[t] <= solar_kwh[t]
    - Battery limits: 0 <= b_ch[t]  <= max_charge_kwh_per_hour
                      0 <= b_dis[t] <= max_discharge_kwh_per_hour
                      minimum_energy_kwh <= b_level[t] <= capacity_kwh
    - Battery dynamics:
            b_level[t] == b_level[t-1] + b_ch[t] - b_dis[t]
            (with b_level[0] fixed to initial_energy_kwh)
    - Day-end cyclic: b_level[T-1] == initial_energy_kwh
                      (battery-ke free source hisebe use kora jabe na)

Objective: minimize sum(g[t] * tariff[t])

Directive apply korar shomoy sudhu 'max_grid_window' eta-r moddhe
upper-bound hisebe ashe — baki directives (solar_reduction etc.)
input data modify kore apply kora hoyeche upore theke.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Tuple

import numpy as np
from scipy.optimize import linprog


@dataclass
class OptimizerInput:
    hours: List[Dict]   # each: {hour, demand_kwh, solar_kwh, tariff_bdt_per_kwh}
    battery: Dict       # capacity_kwh, initial_energy_kwh, minimum_energy_kwh,
                        # max_charge_kwh_per_hour, max_discharge_kwh_per_hour
    max_grid_windows: List[Tuple[int, int]] = None  # list of (start_hour, end_hour)


@dataclass
class OptimizerResult:
    hourly_plan: List[Dict]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    status: str


def optimize(input_data: OptimizerInput) -> OptimizerResult:
    T = len(input_data.hours)
    if T == 0:
        return OptimizerResult([], 0.0, 0.0, 0.0, "empty")

    demand = np.array([h["demand_kwh"] for h in input_data.hours], dtype=float)
    solar_avail = np.array([h["solar_kwh"] for h in input_data.hours], dtype=float)
    tariff = np.array([h["tariff_bdt_per_kwh"] for h in input_data.hours], dtype=float)

    cap = float(input_data.battery["capacity_kwh"])
    init = float(input_data.battery["initial_energy_kwh"])
    bmin = float(input_data.battery["minimum_energy_kwh"])
    ch_max = float(input_data.battery["max_charge_kwh_per_hour"])
    dis_max = float(input_data.battery["max_discharge_kwh_per_hour"])

    # var layout: [g (T), s (T), b_ch (T), b_dis (T), b_level (T)]
    n = 5 * T

    # objective: minimize sum(g[t] * tariff[t])
    c = np.zeros(n)
    c[0:T] = tariff

    # bounds
    bounds = []
    bounds.extend([(0, None)] * T)                                       # g
    bounds.extend([(0, float(solar_avail[t])) for t in range(T)])         # s
    bounds.extend([(0, ch_max)] * T)                                      # b_ch
    bounds.extend([(0, dis_max)] * T)                                    # b_dis
    bounds.extend([(bmin, cap)] * T)                                      # b_level

    # equalities
    A_eq = []
    b_eq = []

    # 1) energy balance per hour: g + s + b_dis - b_ch = demand
    for t in range(T):
        row = np.zeros(n)
        row[t] = 1.0
        row[T + t] = 1.0
        row[2 * T + t] = -1.0
        row[3 * T + t] = 1.0
        A_eq.append(row)
        b_eq.append(demand[t])

    # 2a) b_level[0] = init
    row = np.zeros(n)
    row[4 * T + 0] = 1.0
    A_eq.append(row)
    b_eq.append(init)

    # 2b) dynamics: b_level[t] - b_level[t-1] - b_ch[t] + b_dis[t] = 0  for t >= 1
    for t in range(1, T):
        row = np.zeros(n)
        row[4 * T + t] = 1.0
        row[4 * T + (t - 1)] = -1.0
        row[2 * T + t] = -1.0
        row[3 * T + t] = 1.0
        A_eq.append(row)
        b_eq.append(0.0)

    # 2c) day-end cyclic: b_level[T-1] == init
    row = np.zeros(n)
    row[4 * T + (T - 1)] = 1.0
    A_eq.append(row)
    b_eq.append(init)

    # inequalities (max_grid_window)
    A_ub = []
    b_ub = []
    if input_data.max_grid_windows:
        for (start, end) in input_data.max_grid_windows:
            for t in range(max(0, start), min(T, end + 1)):
                row = np.zeros(n)
                row[t] = 1.0
                A_ub.append(row)
                b_ub.append(demand[t])  # ceiling: at most demand (rest by solar+battery)

    A_eq = np.array(A_eq)
    b_eq = np.array(b_eq)
    A_ub = np.array(A_ub) if A_ub else None
    b_ub = np.array(b_ub) if b_ub else None

    res = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )

    if not res.success:
        return OptimizerResult([], 0.0, 0.0, 0.0, f"failed: {res.message}")

    x = res.x
    g = x[0:T]
    s = x[T:2 * T]
    b_ch = x[2 * T:3 * T]
    b_dis = x[3 * T:4 * T]
    b_lvl = x[4 * T:5 * T]

    hourly_plan: List[Dict] = []
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for t, h in enumerate(input_data.hours):
        ch = float(b_ch[t])
        dis = float(b_dis[t])
        if ch > 1e-6 and dis > 1e-6:
            action = "charging_and_discharging"
        elif ch > 1e-6:
            action = "charging"
        elif dis > 1e-6:
            action = "discharging"
        else:
            action = "idle"

        entry = {
            "hour": int(h["hour"]),
            "grid_kwh": round(float(g[t]), 4),
            "solar_used_kwh": round(float(s[t]), 4),
            "battery_action": action,
            "battery_kwh": round(ch, 4),
            "battery_discharge_kwh": round(dis, 4),
            "battery_energy_after_kwh": round(float(b_lvl[t]), 4),
        }
        hourly_plan.append(entry)
        total_grid += float(g[t])
        total_cost += float(g[t]) * float(tariff[t])
        peak_grid = max(peak_grid, float(g[t]))

    return OptimizerResult(
        hourly_plan=hourly_plan,
        total_grid_kwh=round(total_grid, 4),
        total_cost_bdt=round(total_cost, 4),
        peak_grid_kwh=round(peak_grid, 4),
        status="ok",
    )


def _selftest() -> None:
    """2-hour toy problem — cheap solar, expensive evening peak."""
    inp = OptimizerInput(
        hours=[
            {"hour": 0, "demand_kwh": 10.0, "solar_kwh": 5.0, "tariff_bdt_per_kwh": 8.0},
            {"hour": 1, "demand_kwh": 10.0, "solar_kwh": 5.0, "tariff_bdt_per_kwh": 12.0},
        ],
        battery={
            "capacity_kwh": 10.0,
            "initial_energy_kwh": 5.0,
            "minimum_energy_kwh": 0.0,
            "max_charge_kwh_per_hour": 5.0,
            "max_discharge_kwh_per_hour": 5.0,
        },
    )
    out = optimize(inp)
    assert out.status == "ok", out.status
    print("selftest OK | total_grid =", out.total_grid_kwh,
          "kWh | cost =", out.total_cost_bdt, "BDT")
    for row in out.hourly_plan:
        print(" ", row)


if __name__ == "__main__":
    _selftest()
