# Component Registry & Legacy Migration Mapping

## 1. Component Registry

| Foundation / Layer | Module | Primary Symbols | Responsibility |
|---|---|---|---|
| **Semantic Foundation** | `chubb.semantic_foundation.temporal_registry` | `TemporalRegistry`, `load_actuarial_rules`, `normalize_text` | Valid years (`2020–2024`), base/default year, NFD normalization. |
| **Semantic Foundation** | `chubb.semantic_foundation.metric_registry` | `MetricRegistry` | Canonical metric definitions, units, labels, and keyword matching. |
| **Semantic Foundation** | `chubb.semantic_foundation.entity_resolver` | `EntityResolver` | 32-state entity extraction, alias resolution, longest-span disambiguation. |
| **Semantic Foundation** | `chubb.semantic_foundation.actuarial_catalog` | `ActuarialCatalog` | Unified semantic catalog facade. |
| **Analytical Foundation** | `chubb.analytical_foundation.calculations` | `round_half_up_decimal`, `format_number`, `compute_category_from_rule`, `display_category_label` | IEEE-754 shortest decimal `ROUND_HALF_UP` formatter and threshold evaluation. |
| **Analytical Foundation** | `chubb.analytical_foundation.aggregations` | `compute_national_reference`, `compute_competition_ranks`, `is_valid_severity`, `is_valid_mdp` | National reference means and competition tie rankings (`1, 1, 3`). |
| **Analytical Foundation** | `chubb.analytical_foundation.data_repository` | `DataRepository` | Abstract protocol decoupling storage from calculations. |
| **Analytical Foundation** | `chubb.analytical_foundation.actuarial_engine` | `ActuarialOperationsEngine` | Executive summaries, multi-state comparisons, Pareto, CAGR, and recommendations. |
| **Validation Foundation** | `chubb.validation_foundation.data_validator` | `ActuarialDataValidator` | Dataset schema & referential integrity validator (SSOT). |
| **Validation Foundation** | `chubb.validation_foundation.query_validator` | `QueryValidator` | Pre-execution `QueryIR` validator. |
| **Validation Foundation** | `chubb.validation_foundation.result_validator` | `ResultValidator` | Structured metric slot validator. |
| **Validation Foundation** | `chubb.validation_foundation.output_verifier` | `ActuarialOutputVerifier` | Post-generation numeric verifier and `S0` semantic slot (`LABEL_SWAP_ERROR`) auditor. |
| **Conversational AI** | `chubb.conversational_ai.memory_manager` | `ConversationMemoryManager` | Confirmed vs. pending conversational state and temporal inheritance. |
| **Conversational AI** | `chubb.conversational_ai.query_parser` | `ActuarialQueryParser` | Natural language to structured `QueryIR` parser. |
| **Conversational AI** | `chubb.conversational_ai.grounding` | `build_human_narrative`, `format_executive_summary_response`, `format_recommendations_response`, `format_business_rules_response` | Grounded narrative synthesis and tabular formatting. |
| **Conversational AI** | `chubb.conversational_ai.assistant` | `GroundedActuarialAssistant`, `LlamaColabDataAgent` | Main conversational orchestrator and Colab/Notebook agent wrapper. |
| **Conversational AI** | `chubb.conversational_ai.providers` | `LLMProvider`, `MockLlama3Provider`, `OllamaProvider`, `OpenAICompatibleProvider` | Pluggable LLM provider adapters. |
| **Contracts** | `chubb.contracts` | `QueryIR`, `AnalyticalResult`, `StructuredMetricSlot`, `ErrorCode`, `DataIntegrityError`, `QueryValidationError`, `HallucinationDetectedError`, `LabelSwapDetectedError` | Explicit cross-foundation contracts and exceptions. |
| **Infrastructure** | `chubb.infrastructure` | `JsonDataRepository`, `resolve_data_path`, `resolve_rules_path` | Path resolution and JSON storage adapter. |

---

## 2. Migration Mapping (Before $\to$ After)

| Legacy Location | New Canonical Location | Compatibility Strategy |
|---|---|---|
| `src/actuarial_core.py` | `src/chubb/{semantic_foundation,analytical_foundation,validation_foundation}/` | `src/actuarial_core.py` preserved as re-export facade. |
| `src/llm_grounding.py` | `src/chubb/{conversational_ai,validation_foundation,contracts}/` | `src/llm_grounding.py` preserved as re-export facade. |
| `src/ai_assistant_llm.py` | `src/chubb/conversational_ai/assistant.py` | `src/ai_assistant_llm.py` preserved as re-export facade. |
| `config/actuarial_rules.json` | `config/business_rules/actuarial_rules.json` + `config/semantic/*.json` | Both paths maintained and verified identical via SHA-256. |
| `data.json` | `data/curated/data.json` | Both paths maintained and verified identical via SHA-256. |
| `data/baseline_siniestros.csv` | `data/raw/baseline_siniestros.csv` | Preserved in both locations. |
| `data/mexico_estados.geojson` | `data/raw/mexico_estados.geojson` | Preserved in both locations. |
| `index.html`, `css/`, `js/`, `assets/` | `app/index.html`, `app/css/`, `app/js/`, `app/assets/` | Served seamlessly by `scripts/dev_server.py`. |
| `src/generate_json.py`, `src/build_mexico_map_svg.py` | `pipelines/generate_json.py`, `pipelines/build_mexico_map_svg.py` | Copied to `pipelines/`. |
| `src/dev_server.py` | `scripts/dev_server.py` | `src/dev_server.py` delegates to `scripts/dev_server.py`. |
| `tests/benchmark_10k/` | `tests/performance/benchmark_10k/` | Preserved in both locations for CI and legacy scripts. |

