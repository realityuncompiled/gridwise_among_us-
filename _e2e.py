"""End-to-end test in single process — uses FastAPI TestClient (no real port)."""
import json
import sys
sys.path.insert(0, r"D:\Deshneta")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# 1) /health
r = client.get("/health")
print("=== /health ===")
print("status:", r.status_code, "body:", r.json())

# 2) /optimize-energy
SCENARIO = {
    "scenario_id": "test_day_1",
    "operator_notes": [
        "দুপুর ১টা থেকে ৩টা পর্যন্ত সোলার কম থাকবে, প্রায় ৩০ ভাগ",
        "Battery তে অন্তত ৩০ kWh রিজার্ভ রাখতে হবে",
        "9pm to 11pm battery charge করা যাবে না",
        "Cafeteria menu is changing next week",
    ],
    "hours": [
        {"hour": h,
         "demand_kwh": 50 + (h % 6) * 5,
         "solar_kwh": 20 if 8 <= h <= 18 else 0,
         "tariff_bdt_per_kwh": 8.0 if h < 18 else 18.0}
        for h in range(24)
    ],
    "battery": {
        "capacity_kwh": 80.0,
        "initial_energy_kwh": 40.0,
        "minimum_energy_kwh": 0.0,
        "max_charge_kwh_per_hour": 25.0,
        "max_discharge_kwh_per_hour": 25.0,
    },
}

print("\n=== POST /optimize-energy ===")
r = client.post("/optimize-energy", json=SCENARIO)
print("status:", r.status_code)

if r.status_code != 200:
    print("ERROR body:", r.text)
    sys.exit(1)

body = r.json()
print("\n=== DIRECTIVE INTERPRETATIONS ===")
for d in body["directive_interpretation"]:
    print(f"  note[{d['note_index']}] applies={d['applies']} type={d['directive_type']} "
          f"adj={d['structured_adjustment']}")
    print(f"      -> {d['explanation']}")

print("\n=== KEY METRICS ===")
print(f"  total_grid: {body['total_grid_kwh']} kWh")
print(f"  total_cost: BDT {body['total_cost_bdt']}")
print(f"  peak_grid : {body['peak_grid_kwh']} kWh")
print(f"  summary   : {body['plan_summary']}")

print("\n=== HOURLY PLAN (first 3 + last 3) ===")
plan = body["hourly_plan"]
for row in plan[:3] + plan[-3:]:
    print(f"  h{row['hour']:02d} grid={row['grid_kwh']:.2f}  solar={row['solar_used_kwh']:.2f}  "
          f"action={row['battery_action']:<28} batt_after={row['battery_energy_after_kwh']:.2f}")
