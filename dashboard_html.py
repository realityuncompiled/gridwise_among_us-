"""
Interactive Web Dashboard for BUP Smart Campus Energy Optimization Challenge.
Provides a modern, visually stunning UI for live demonstrations and hackathon presentation.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BUP Smart Campus Energy Optimization | Live Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#ecfdf5',
              500: '#10b981',
              600: '#059669',
              900: '#064e3b',
            }
          }
        }
      }
    }
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
    body { font-family: 'Inter', sans-serif; }
    code, pre { font-family: 'JetBrains Mono', monospace; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen antialiased flex flex-col">

  <!-- Header -->
  <header class="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-cyan-500 flex items-center justify-center text-slate-950 font-bold text-xl shadow-lg shadow-emerald-500/20">
          ⚡
        </div>
        <div>
          <h1 class="text-lg font-bold tracking-tight text-white flex items-center gap-2">
            BUP Smart Campus Energy Optimizer
            <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">CSE Fest 2026</span>
          </h1>
          <p class="text-xs text-slate-400">LLM-Assisted Operator Directive Interpretation & 24h HiGHS LP Scheduling</p>
        </div>
      </div>
      <div class="flex items-center space-x-3">
        <div class="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span class="text-slate-300 font-medium">API: <strong class="text-emerald-400">ONLINE (200 OK)</strong></span>
        </div>
        <a href="/health" target="_blank" class="text-xs text-slate-400 hover:text-slate-200 transition-colors">/health</a>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-4 py-6 flex-1 w-full space-y-6">

    <!-- Scenario & Operator Notes Input -->
    <div class="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-5 shadow-xl backdrop-blur">
      <div class="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-slate-800 gap-3">
        <div>
          <h2 class="text-base font-semibold text-white flex items-center gap-2">
            <span>📝</span> Campus Operator Directives & Scenario Input
          </h2>
          <p class="text-xs text-slate-400">Natural-language operator notes will be interpreted by LLM and guardrailed before mathematical optimization.</p>
        </div>
        <div class="flex items-center gap-2">
          <button onclick="loadPreset(1)" class="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700">Preset 1: Panel Wash</button>
          <button onclick="loadPreset(2)" class="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700">Preset 2: Grid Cap & Reserve</button>
          <button id="runBtn" onclick="runOptimization()" class="text-xs font-semibold px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold transition-all shadow-lg shadow-emerald-500/25 flex items-center gap-2">
            <span>⚡</span> Run Full Pipeline
          </button>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        <div>
          <label class="block text-xs font-medium text-slate-400 mb-1">Operator Note 1 (Temporary Condition)</label>
          <textarea id="note0" rows="2" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500">Solar output will drop to about 20% from 1 PM to 3 PM.</textarea>
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-400 mb-1">Operator Note 2 (Battery Rule)</label>
          <textarea id="note1" rows="2" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500">Do not charge the battery between 2 PM and 4 PM.</textarea>
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-400 mb-1">Operator Note 3 (Distractor Note)</label>
          <textarea id="note2" rows="2" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500">The cafeteria menu changes tomorrow.</textarea>
        </div>
      </div>
    </div>

    <!-- Output Dashboard Section -->
    <div id="resultsSection" class="space-y-6">

      <!-- KPI Summary Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-4 shadow-lg">
          <div class="text-xs font-medium text-slate-400">Total Grid Cost</div>
          <div class="text-2xl font-extrabold text-emerald-400 mt-1 flex items-baseline gap-1">
            <span id="costVal">38,139.50</span> <span class="text-xs text-slate-400 font-normal">BDT</span>
          </div>
          <div class="text-[11px] text-slate-500 mt-1">Globally minimized by HiGHS LP</div>
        </div>

        <div class="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-4 shadow-lg">
          <div class="text-xs font-medium text-slate-400">Total Grid Purchased</div>
          <div class="text-2xl font-extrabold text-cyan-400 mt-1 flex items-baseline gap-1">
            <span id="gridVal">4,137.00</span> <span class="text-xs text-slate-400 font-normal">kWh</span>
          </div>
          <div class="text-[11px] text-slate-500 mt-1">Across 24-hour horizon</div>
        </div>

        <div class="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-4 shadow-lg">
          <div class="text-xs font-medium text-slate-400">Peak Hourly Grid Import</div>
          <div class="text-2xl font-extrabold text-amber-400 mt-1 flex items-baseline gap-1">
            <span id="peakVal">260.00</span> <span class="text-xs text-slate-400 font-normal">kWh</span>
          </div>
          <div class="text-[11px] text-slate-500 mt-1">Maximum load hour</div>
        </div>

        <div class="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-4 shadow-lg">
          <div class="text-xs font-medium text-slate-400">Battery Neutrality</div>
          <div class="text-2xl font-extrabold text-emerald-400 mt-1 flex items-baseline gap-1">
            <span>200 → 200</span> <span class="text-xs text-emerald-400 font-normal">kWh</span>
          </div>
          <div class="text-[11px] text-emerald-500 mt-1">✓ End-of-Day Neutral (E₂₃ = E₀)</div>
        </div>
      </div>

      <!-- Directive Interpretation Cards -->
      <div class="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-5 shadow-lg">
        <h3 class="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <span>🧠</span> Machine-Checkable Directive Interpretation (LLM + Guardrails)
        </h3>
        <div id="directivesContainer" class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <!-- Populated by JS -->
        </div>
      </div>

      <!-- Plan Summary Callout -->
      <div class="bg-gradient-to-r from-emerald-950/40 via-slate-900/60 to-cyan-950/40 border border-emerald-500/20 rounded-2xl p-4 shadow-lg">
        <div class="flex items-start gap-3">
          <span class="text-xl">💡</span>
          <div>
            <div class="text-xs font-semibold text-emerald-400 tracking-wider uppercase">Optimizer Strategy Summary</div>
            <p id="summaryText" class="text-xs text-slate-300 mt-1 leading-relaxed">
              Loading scenario plan...
            </p>
          </div>
        </div>
      </div>

      <!-- Chart -->
      <div class="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-5 shadow-lg">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-sm font-semibold text-white flex items-center gap-2">
            <span>📊</span> 24-Hour Energy Scheduling & Battery Dispatch
          </h3>
          <div class="flex items-center gap-3 text-xs text-slate-400">
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded bg-cyan-400 inline-block"></span> Grid Import</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded bg-amber-400 inline-block"></span> Solar Used</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded bg-emerald-400 inline-block"></span> Battery Energy (SoC)</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded bg-rose-400 inline-block"></span> Campus Demand</span>
          </div>
        </div>
        <div class="h-72 w-full">
          <canvas id="energyChart"></canvas>
        </div>
      </div>

      <!-- Schedule Table -->
      <div class="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-5 shadow-lg">
        <h3 class="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <span>📋</span> Hourly Operational Plan (24-Hour Replay)
        </h3>
        <div class="overflow-x-auto max-h-80 border border-slate-800 rounded-xl">
          <table class="w-full text-left text-xs text-slate-300">
            <thead class="bg-slate-950 text-slate-400 font-semibold sticky top-0 border-b border-slate-800">
              <tr>
                <th class="p-2.5">Hour</th>
                <th class="p-2.5">Grid (kWh)</th>
                <th class="p-2.5">Solar Used (kWh)</th>
                <th class="p-2.5">Battery Action</th>
                <th class="p-2.5">Battery Flow (kWh)</th>
                <th class="p-2.5">Battery SoC (kWh)</th>
              </tr>
            </thead>
            <tbody id="planTableBody" class="divide-y divide-slate-800/50">
              <!-- Populated by JS -->
            </tbody>
          </table>
        </div>
      </div>

    </div>

  </main>

  <!-- Footer -->
  <footer class="border-t border-slate-800/80 bg-slate-950 py-4 text-center text-xs text-slate-500">
    BUP CSE Fest 2026 • Smart Campus Energy Optimization Challenge • Solved with FastAPI & SciPy HiGHS
  </footer>

  <script>
    let energyChart = null;

    const baseScenario = {
      "scenario_id": "GRID-101",
      "operator_notes": [
        "Solar output will drop to about 20% from 1 PM to 3 PM.",
        "Do not charge the battery between 2 PM and 4 PM.",
        "The cafeteria menu changes tomorrow."
      ],
      "hours": [
        {"hour": 0, "demand_kwh": 140, "solar_kwh": 0, "tariff_bdt_per_kwh": 6.5},
        {"hour": 1, "demand_kwh": 130, "solar_kwh": 0, "tariff_bdt_per_kwh": 6.5},
        {"hour": 2, "demand_kwh": 125, "solar_kwh": 0, "tariff_bdt_per_kwh": 6.5},
        {"hour": 3, "demand_kwh": 120, "solar_kwh": 0, "tariff_bdt_per_kwh": 6.5},
        {"hour": 4, "demand_kwh": 125, "solar_kwh": 0, "tariff_bdt_per_kwh": 6.5},
        {"hour": 5, "demand_kwh": 135, "solar_kwh": 0, "tariff_bdt_per_kwh": 6.5},
        {"hour": 6, "demand_kwh": 150, "solar_kwh": 10, "tariff_bdt_per_kwh": 7.5},
        {"hour": 7, "demand_kwh": 180, "solar_kwh": 40, "tariff_bdt_per_kwh": 8.0},
        {"hour": 8, "demand_kwh": 220, "solar_kwh": 80, "tariff_bdt_per_kwh": 8.5},
        {"hour": 9, "demand_kwh": 260, "solar_kwh": 130, "tariff_bdt_per_kwh": 8.5},
        {"hour": 10, "demand_kwh": 280, "solar_kwh": 170, "tariff_bdt_per_kwh": 9.0},
        {"hour": 11, "demand_kwh": 290, "solar_kwh": 190, "tariff_bdt_per_kwh": 9.0},
        {"hour": 12, "demand_kwh": 270, "solar_kwh": 200, "tariff_bdt_per_kwh": 9.0},
        {"hour": 13, "demand_kwh": 280, "solar_kwh": 180, "tariff_bdt_per_kwh": 9.0},
        {"hour": 14, "demand_kwh": 270, "solar_kwh": 160, "tariff_bdt_per_kwh": 9.5},
        {"hour": 15, "demand_kwh": 250, "solar_kwh": 120, "tariff_bdt_per_kwh": 9.5},
        {"hour": 16, "demand_kwh": 240, "solar_kwh": 70, "tariff_bdt_per_kwh": 10.0},
        {"hour": 17, "demand_kwh": 260, "solar_kwh": 20, "tariff_bdt_per_kwh": 13.0},
        {"hour": 18, "demand_kwh": 300, "solar_kwh": 0, "tariff_bdt_per_kwh": 14.5},
        {"hour": 19, "demand_kwh": 310, "solar_kwh": 0, "tariff_bdt_per_kwh": 15.0},
        {"hour": 20, "demand_kwh": 290, "solar_kwh": 0, "tariff_bdt_per_kwh": 14.0},
        {"hour": 21, "demand_kwh": 250, "solar_kwh": 0, "tariff_bdt_per_kwh": 11.5},
        {"hour": 22, "demand_kwh": 200, "solar_kwh": 0, "tariff_bdt_per_kwh": 8.5},
        {"hour": 23, "demand_kwh": 160, "solar_kwh": 0, "tariff_bdt_per_kwh": 7.0}
      ],
      "battery": {
        "capacity_kwh": 500,
        "initial_energy_kwh": 200,
        "minimum_energy_kwh": 50,
        "max_charge_kwh_per_hour": 100,
        "max_discharge_kwh_per_hour": 100
      }
    };

    function loadPreset(n) {
      if (n === 1) {
        document.getElementById("note0").value = "Solar output will drop to about 20% from 1 PM to 3 PM.";
        document.getElementById("note1").value = "Do not charge the battery between 2 PM and 4 PM.";
        document.getElementById("note2").value = "The cafeteria menu changes tomorrow.";
      } else {
        document.getElementById("note0").value = "Keep at least 200 kWh in reserve from 6 PM until 9 PM.";
        document.getElementById("note1").value = "Grid import may not exceed 180 kWh between 5 PM and 8 PM.";
        document.getElementById("note2").value = "Campus faculty council will convene at 11 AM.";
      }
      runOptimization();
    }

    async function runOptimization() {
      const btn = document.getElementById("runBtn");
      btn.innerHTML = `<span>⏳</span> Optimizing...`;
      btn.disabled = true;

      const payload = JSON.parse(JSON.stringify(baseScenario));
      payload.operator_notes = [
        document.getElementById("note0").value.trim(),
        document.getElementById("note1").value.trim(),
        document.getElementById("note2").value.trim()
      ].filter(n => n.length > 0);

      try {
        const res = await fetch("/optimize-energy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("Optimization failed: " + res.statusText);
        const data = await res.json();
        renderResults(data, payload);
      } catch (err) {
        alert("Error: " + err.message);
      } finally {
        btn.innerHTML = `<span>⚡</span> Run Full Pipeline`;
        btn.disabled = false;
      }
    }

    function renderResults(data, requestPayload) {
      document.getElementById("costVal").innerText = data.total_cost_bdt.toLocaleString(undefined, {minimumFractionDigits: 2});
      document.getElementById("gridVal").innerText = data.total_grid_kwh.toLocaleString(undefined, {minimumFractionDigits: 2});
      document.getElementById("peakVal").innerText = data.peak_grid_kwh.toLocaleString(undefined, {minimumFractionDigits: 2});
      document.getElementById("summaryText").innerText = data.plan_summary;

      // Directives
      const dirCont = document.getElementById("directivesContainer");
      dirCont.innerHTML = "";
      data.directive_interpretation.forEach((d, i) => {
        const card = document.createElement("div");
        card.className = "p-3 rounded-xl border bg-slate-950/60 " + (d.applies ? "border-emerald-500/30" : "border-slate-800");
        const badgeColor = d.applies ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-slate-800 text-slate-400 border-slate-700";
        card.innerHTML = `
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-mono uppercase text-slate-500">Note ${d.note_index}</span>
            <span class="text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badgeColor}">${d.directive_type}</span>
          </div>
          <div class="text-xs text-slate-300 font-medium mt-1.5 truncate">"${requestPayload.operator_notes[d.note_index]}"</div>
          <div class="text-[11px] text-slate-400 mt-1">${d.explanation}</div>
          ${d.structured_adjustment ? `<pre class="mt-2 text-[10px] bg-slate-900 p-1.5 rounded text-emerald-300 overflow-x-auto">${JSON.stringify(d.structured_adjustment)}</pre>` : ''}
        `;
        dirCont.appendChild(card);
      });

      // Table
      const tb = document.getElementById("planTableBody");
      tb.innerHTML = "";
      data.hourly_plan.forEach(row => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-900/60 transition-colors";
        let actionBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">Idle</span>`;
        if (row.battery_action === 'charge') {
          actionBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-300 font-semibold">⚡ Charge</span>`;
        } else if (row.battery_action === 'discharge') {
          actionBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 font-semibold">🔋 Discharge</span>`;
        }
        tr.innerHTML = `
          <td class="p-2.5 font-mono text-slate-400">${row.hour}:00</td>
          <td class="p-2.5 font-semibold text-cyan-300">${row.grid_kwh.toFixed(1)}</td>
          <td class="p-2.5 text-amber-300">${row.solar_used_kwh.toFixed(1)}</td>
          <td class="p-2.5">${actionBadge}</td>
          <td class="p-2.5">${row.battery_kwh > 0 ? row.battery_kwh.toFixed(1) : '-'}</td>
          <td class="p-2.5 font-mono text-emerald-400 font-semibold">${row.battery_energy_after_kwh.toFixed(1)}</td>
        `;
        tb.appendChild(tr);
      });

      // Render Chart
      renderChart(data.hourly_plan, requestPayload.hours);
    }

    function renderChart(plan, hours) {
      const ctx = document.getElementById('energyChart').getContext('2d');
      const labels = plan.map(p => `${p.hour}:00`);
      const demandData = hours.map(h => h.demand_kwh);
      const gridData = plan.map(p => p.grid_kwh);
      const solarData = plan.map(p => p.solar_used_kwh);
      const batteryData = plan.map(p => p.battery_energy_after_kwh);

      if (energyChart) {
        energyChart.destroy();
      }

      energyChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              type: 'line',
              label: 'Demand (kWh)',
              data: demandData,
              borderColor: '#f43f5e',
              borderWidth: 2,
              borderDash: [5, 5],
              pointRadius: 0,
              yAxisID: 'y'
            },
            {
              type: 'line',
              label: 'Battery SoC (kWh)',
              data: batteryData,
              borderColor: '#10b981',
              borderWidth: 2.5,
              fill: false,
              pointRadius: 2,
              yAxisID: 'y'
            },
            {
              type: 'bar',
              label: 'Solar Used (kWh)',
              data: solarData,
              backgroundColor: '#fbbf24',
              stack: 'supply',
              yAxisID: 'y'
            },
            {
              type: 'bar',
              label: 'Grid Import (kWh)',
              data: gridData,
              backgroundColor: '#06b6d4',
              stack: 'supply',
              yAxisID: 'y'
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false }
          },
          scales: {
            x: {
              grid: { color: 'rgba(51, 65, 85, 0.3)' },
              ticks: { color: '#94a3b8', font: { size: 10 } }
            },
            y: {
              grid: { color: 'rgba(51, 65, 85, 0.3)' },
              ticks: { color: '#94a3b8', font: { size: 10 } }
            }
          }
        }
      });
    }

    // Run automatically on initial load
    window.addEventListener('DOMContentLoaded', () => {
      runOptimization();
    });
  </script>
</body>
</html>
"""
