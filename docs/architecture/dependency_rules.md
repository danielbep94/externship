# Dependency Rules & Architectural Boundaries

## 1. Allowed Dependency Direction

Dependencies flow strictly top-down:

1. **Presentation (`app/`, CLI, Notebooks)** $\to$ `conversational_ai`, `analytical_foundation`, `contracts`
2. **Conversational AI (`chubb.conversational_ai`)** $\to$ `contracts`, `semantic_foundation`, `validation_foundation`, `analytical_foundation`, `infrastructure`
3. **Validation Foundation (`chubb.validation_foundation`)** $\to$ `contracts`, `semantic_foundation`, `analytical_foundation`, `infrastructure`
4. **Analytical Foundation (`chubb.analytical_foundation`)** $\to$ Python standard library (`math`, `decimal`, `typing`)
5. **Semantic Foundation (`chubb.semantic_foundation`)** $\to$ `infrastructure.paths` and `config/` JSON files
6. **Contracts (`chubb.contracts`)** $\to$ Python standard library (`dataclasses`, `typing`)

---

## 2. Strictly Prohibited Dependencies (Enforced by Quality Gate `QG-02`)

| Source Module | Prohibited Target | Reason |
|---|---|---|
| `semantic_foundation` | `analytical_foundation`, `validation_foundation`, `conversational_ai` | Semantic catalogs must remain pure definitions without calculation or LLM coupling. |
| `analytical_foundation` | `conversational_ai`, `validation_foundation` | The actuarial calculation engine must run standalone without LLM or NL parser dependencies. |
| `validation_foundation` | `conversational_ai` | Validators must audit contracts and outputs independently of the conversational orchestrator. |
| `contracts` | Any other foundation | Contracts are pure data structures shared across boundaries. |

Automated verification is executed via AST import analysis in `scripts/run_quality_gates.py`.

