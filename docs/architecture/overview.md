# Architecture Overview — CHUBB Modular Monolith with Four Foundations

## 1. Executive Summary

The **CHUBB Actuarial Analytics & Conversational AI** repository is structured as a **Modular Monolith** organized around four core Foundations, explicit cross-module contracts, and a storage-decoupled infrastructure layer.

```mermaid
flowchart TD
    UI["Presentation Layer\n(app/ HTML/JS Today · Streamlit on Databricks Tomorrow)"]
    CAI["Conversational AI Foundation\n(src/chubb/conversational_ai/)"]
    VAL["Validation Foundation\n(src/chubb/validation_foundation/)"]
    CNT["Contracts Foundation\n(src/chubb/contracts/)"]
    SEM["Semantic Foundation\n(src/chubb/semantic_foundation/)"]
    ANA["Analytical Foundation\n(src/chubb/analytical_foundation/)"]
    INF["Infrastructure Layer\n(src/chubb/infrastructure/)"]
    CFG["Business & Semantic Config\n(config/semantic/ & config/business_rules/)"]
    DAT["Curated Dataset\n(data/curated/data.json Today · Unity Catalog Delta Tomorrow)"]

    UI --> CAI
    CAI --> CNT
    CAI --> SEM
    CAI --> VAL
    CAI --> ANA
    VAL --> CNT
    VAL --> SEM
    VAL --> ANA
    ANA --> INF
    SEM --> CFG
    INF --> DAT
```

---

## 2. The Four Foundations

| Foundation | Package Path | Core Responsibility | Architectural Restriction |
|---|---|---|---|
| **1. Semantic Foundation** | `src/chubb/semantic_foundation/` | Governs what data means: canonical entities, aliases, metrics, units, and temporal rules. | Never executes actuarial calculations or calls LLM providers. |
| **2. Analytical Foundation** | `src/chubb/analytical_foundation/` | Governs how results are computed: `ROUND_HALF_UP` math, rankings, Pareto, CAGR, executive summaries, and recommendations. | Operates 100% deterministically without any LLM or frontend dependency. |
| **3. Validation Foundation** | `src/chubb/validation_foundation/` | Governs reliability and auditability: schema validation, pre-execution `QueryIR` validation, result slot validation, and `S0` hallucination/label-swap guardrails. | Never silently alters analytical values. |
| **4. Conversational AI** | `src/chubb/conversational_ai/` | Governs natural language understanding, conversational memory, grounded response synthesis, and optional LLM providers. | Never calculates actuarial metrics directly; delegates all math to `Analytical Foundation`. |

---

## 3. Supporting Layers

- **Contracts (`src/chubb/contracts/`)**: Defines `QueryIR`, `AnalyticalResult`, `StructuredMetricSlot`, `ActuarialErrorContract`, and standardized `ErrorCode` constants.
- **Infrastructure (`src/chubb/infrastructure/`)**: Centralizes path resolution (`paths.py`) and storage adapters (`JsonDataRepository` in `json_repository.py`).
- **Backward-Compatibility Facades (`src/actuarial_core.py`, `src/llm_grounding.py`, `src/ai_assistant_llm.py`)**: Re-export all public classes and functions so legacy scripts, notebooks, and tests continue to work without modification.

