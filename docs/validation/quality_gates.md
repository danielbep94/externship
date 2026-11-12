# Quality Gates Specification (`scripts/run_quality_gates.py`)

Every change to the repository must pass all 8 automated Quality Gates with zero errors:

| Gate ID | Name | Verification Target | Acceptance Criterion |
|---|---|---|---|
| **QG-01** | **Data & Config Integrity (SHA-256 & Schema)** | `data/curated/data.json`, `config/business_rules/actuarial_rules.json` | 100% schema validation pass (`ActuarialDataValidator`) and exact parity with root compatibility files. |
| **QG-02** | **Architectural Boundary & Import Audit** | `src/chubb/{semantic,analytical,validation,conversational_ai,contracts}/` | Zero prohibited imports or circular dependencies across Foundations (AST static inspection). |
| **QG-03** | **Compatibility Facade Audit** | `src/actuarial_core.py`, `src/llm_grounding.py`, `src/ai_assistant_llm.py` | All public symbols importable and bound to canonical Foundation classes. |
| **QG-04** | **Unit, Integration, Golden & Adversarial Tests** | `tests/` (`unittest discover`) | 100% pass across all unit, integration, golden, and adversarial test cases. |
| **QG-05** | **Canonical Output Audit** | `src/validate_assistant_outputs.py` | 13/13 (100%) canonical checks pass against `data.json`. |
| **QG-06** | **Python–JavaScript Mathematical Parity** | `tests/parity/test_parity.mjs` | 35/35 (100%) parity vectors match between Python and JavaScript engines. |
| **QG-07** | **10K Independent Oracle Benchmark** | `tests/performance/benchmark_10k/run_benchmark_10k.py` | 10,000 queries evaluated against `independent_oracle.py` with 100.00% numerical accuracy and `0` `S0` errors. |
| **QG-08** | **HTTP Dev Server Routing & Path Traversal Guard** | `scripts/dev_server.py` | Serves `/index.html`, `/data.json`, `/js/actuarial_engine.js` with `Cache-Control: no-store` and blocks `../` traversal. |

