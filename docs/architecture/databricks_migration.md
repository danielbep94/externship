# Databricks & Streamlit Migration Readiness Guide

## 1. Current State: Databricks-Ready Modular Monolith

The repository has been refactored so that all domain semantics, actuarial calculations, validation guardrails, and conversational AI orchestration reside in the pure-Python `chubb` package (`src/chubb/`), completely decoupled from the HTML/JS presentation layer (`app/`) and local JSON storage (`data/curated/data.json`).

---

## 2. Storage Migration: `JsonDataRepository` $\to$ `DeltaDataRepository`

Today, `JsonDataRepository` (`src/chubb/infrastructure/json_repository.py`) implements the `DataRepository` protocol (`src/chubb/analytical_foundation/data_repository.py`).

When deploying to **Azure Databricks with Unity Catalog**:
1. Implement `DeltaDataRepository(DataRepository)` in `src/chubb/infrastructure/delta_repository.py` querying `catalog.schema.actuarial_state_metrics` via `pyspark.sql.SparkSession` or `databricks-sql-connector`.
2. Pass the `DeltaDataRepository` dataset dictionary into `ActuarialDataValidator.validate_data_dict()` and `ActuarialOperationsEngine(data)`.
3. **Zero changes** are required in `semantic_foundation`, `analytical_foundation`, `validation_foundation`, or `conversational_ai`.

---

## 3. Presentation Migration: `app/` HTML/JS $\to$ Databricks Streamlit App

To deploy as an **Azure Databricks App (Streamlit)**:
1. Create `streamlit_app.py` at the repository root or `app/streamlit_app.py`.
2. Import `GroundedActuarialAssistant` directly:
   ```python
   from chubb.conversational_ai import GroundedActuarialAssistant
   assistant = GroundedActuarialAssistant()
   result = assistant.ask_with_metadata(user_prompt)
   ```
3. Render `result["response"]`, `result["structured_metrics"]`, and `result["traceability"]` inside `st.chat_message("assistant")`.

---

## 4. LLM Provider Migration: Local/Mock $\to$ Databricks Model Serving

To connect **Databricks Model Serving** (e.g., `databricks-meta-llama-3-1-70b-instruct`):
1. Instantiate `OpenAICompatibleProvider` (`src/chubb/conversational_ai/providers/openai_compatible.py`) pointing to `https://<workspace-host>/serving-endpoints` with the Databricks PAT or OAuth token.
2. All LLM-generated narratives remain strictly audited by `ActuarialOutputVerifier.verify()` and `ActuarialOutputVerifier.verify_semantic_slots()` (`S0` zero-tolerance guardrail).

