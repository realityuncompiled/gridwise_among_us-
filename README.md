# Smart Campus Energy Optimization Engine ⚡

An intelligent microservice built for the **BUP CSE Fest 2026 Hackathon**. This system processes unstructured grid operation directives using Gemini LLM guardrails, formulates a 24-hour cost minimization Linear Program solved via SciPy HiGHS, and independently audits schedules using a deterministic Replay Validator.

---

## 📌 Project Architecture

```text
gridwise_among_us/
├── app/
│   ├── directives.py         # Deterministic guardrails & constraint validator
│   ├── llm_interpreter.py    # Structured JSON extraction via Gemini LLM
│   ├── optimizer.py          # SciPy HiGHS Linear Programming optimization solver
│   ├── verifier.py           # Replay audit & physical constraint verifier
│   └── schemas.py            # Pydantic data schemas & request models
├── tests/
│   ├── test_directives.py   # Guardrail validation unit tests
│   ├── test_optimizer.py    # LP math solver unit tests
│   └── test_verifier.py     # Verification & audit unit tests
├── requirements.txt          # Project dependencies
└── README.md