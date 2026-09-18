"""End-to-end test: hit /optimize-energy with a realistic 24h scenario."""

import json
import urllib.request


SCENARIO = {
    "scenario_id": "test_day_1",
    "operator_notes": [
        "দুপুর ১টা থেকে ৩টা পর্যন্ত সোলার কম থাকবে, প্রায় ৩০ ভাগ",
        "Battery তে অন্তত ৩০ kWh রিজার্ভ রাখতে হবে",
        "9pm to 11pm battery charge করা যাবে না",
        "Cafeteria menu is changing next week, ping me later",
    ],
    "hours": [
        {"hour": h, "demand_kwh": 50 + (h % 6) * 5, "solar_kwh": 20 if 8 <= h <= 18 else 0,
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


req = urllib.request.Request(
    "http://127.0.0.1:8000/optimize-energy",
    data=json.dumps(SCENARIO).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        parsed = json.loads(body)
        print("STATUS:", resp.status)
        print("\n=== DIRECTIVE INTERPRETATIONS ===")
        for d in parsed["directive_interpretation"]:
            print(f"  note[{d['note_index']}] applies={d['applies']} "
                  f"type={d['directive_type']} adj={d['structured_adjustment']}")
            print(f"      -> {d['explanation']}")
        print("\n=== KEY METRICS ===")
        print(f"  total_grid: {parsed['total_grid_kwh']} kWh")
        print(f"  total_cost: BDT {parsed['total_cost_bdt']}")
        print(f"  peak_grid : {parsed['peak_grid_kwh']} kWh")
        print(f"  summary   : {parsed['plan_summary']}")
        print("\n=== HOURLY PLAN (first/last 3 each) ===")
        plan = parsed["hourly_plan"]
        for row in plan[:3] + ["..."] + plan[-3:]:
            print(" ", row)
except Exception as e:
    print("REQ FAILED:", type(e).__name__, str(e)[:300])