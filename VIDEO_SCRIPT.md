# 3-Minute Architecture & Solution Video Script
### BUP CSE Fest 2026 Hackathon — Preliminary Round

**Target Duration**: Exactly 2:45 to 3:00 minutes.  
**Tone**: Confident, technical, concise, and structured.

---

## Slide & Screen Breakdown

### Segment 1: Problem Overview & Challenge Requirements (0:00 – 0:45)
* **Visual**: Show the challenge title and the 24-hour campus energy curves (Demand, Solar, Tariff) alongside sample operator notes.
* **Speaker Script**:
  > *"Hello everyone! We are presenting our solution for the BUP Smart Campus Energy Optimization Challenge.  
  > The goal is to optimize a 24-hour energy schedule for the campus, balancing grid electricity purchases, rooftop solar generation, and a Battery Energy Storage System to minimize total electricity cost in Bangladeshi Taka (BDT).  
  > Crucially, campus operators send natural-language notes that dictate temporary operational conditions—such as solar panel washing, battery reserve minimums, charging bans, or grid import caps—interspersed with realistic distractor notes.  
  > The core challenge is: we cannot simply trust free-form LLM outputs to do math. Our system bridges the gap between natural language understanding and rigorous mathematical scheduling."*

---

### Segment 2: System Architecture: LLM → Guardrails → LP Optimizer (0:45 – 1:45)
* **Visual**: Show the Architecture Diagram (from README.md) highlighting the 4 distinct stages.
* **Speaker Script**:
  > *"To ensure 100% compliance with the Problem Statement, our architecture consists of four tightly-coupled stages:  
  > **First: LLM Directive Interpretation**. We employ Google Gemini (`gemini-3.8-flash`) via the official `google-genai` SDK using a strict JSON schema prompt. It maps notes into one of 6 supported directive types or `no_op`. For resilience, we built a dual-engine architecture with an offline semantic NLP extractor that guarantees the service never fails if external networks or API keys are unavailable.  
  > **Second: Deterministic Guardrails**. Untrusted LLM output passes through rigorous Python guardrails. We enforce whole-hour $[start, end)$ intervals, ascending sorted arrays in range 0 to 23, bound solar factors between 0 and 1, and ensure `no_op` directives strictly have `applies=false` with null adjustments. Hallucinations are strictly filtered.  
  > **Third: Mathematical Energy Optimization**. We formulate the 24-hour scheduling as a Linear Program (LP) solved with SciPy HiGHS (`scipy.optimize.linprog`). The LP minimizes total grid cost while respecting hourly energy balance, available effective solar, battery state dynamics, rate limits, directive constraints, and strict end-of-day battery neutrality ($E_{23} = E_0$).  
  > **Fourth: Schedule Replay & Verification**. An independent audit module replays all 24 hours, eliminates simultaneous charging and discharging, and recalculates exact totals with zero discrepancies."*

---

### Segment 3: Live Demonstration, Testing & Docker (1:45 – 2:45)
* **Visual**: Terminal showing `pytest tests/ -v` passing all 14 tests, followed by `curl http://localhost:8000/health` and `POST /optimize-energy`.
* **Speaker Script**:
  > *"Here is our live service in action.  
  > Running our automated test suite across 14 comprehensive test cases—including paraphrase robustness, hour extraction, boundary enforcement, and edge case optimization—all 14 pass in just a few seconds.  
  > When we start our FastAPI service and ping `GET /health`, it immediately returns status `ok`.  
  > Sending a sample request to `POST /optimize-energy` with multiple paraphrased notes, our pipeline processes the scenario in under 100 milliseconds—far below the competition's 5-second P95 threshold.  
  > The response returns the structured directive interpretations matching ground truth, the complete 24-hour hourly plan, recalculated cost and peak grid values, and a concise plan summary.  
  > Finally, our solution includes a self-contained multi-stage Dockerfile that binds to port 8000 on 0.0.0.0, ready for immediate pull and evaluation by the judges."*

---

### Segment 4: Wrap-Up (2:45 – 3:00)
* **Visual**: Summary slide with team credentials and key metrics (sub-100ms latency, 100% test pass rate, exact mathematical optimality).
* **Speaker Script**:
  > *"In summary, our solution delivers robust natural language understanding, impenetrable deterministic guardrails, and mathematically optimal energy scheduling. Thank you!"*
