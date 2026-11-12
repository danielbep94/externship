# CHUBB — Estudio Actuarial de Severidad de Siniestros de Auto en México (2020–2024)

**Arquitectura Modular Basada en Cuatro Foundations (`Semantic`, `Analytical`, `Validation`, `Conversational AI`) · Databricks-Ready**

---

## 1. Visión General y Arquitectura

Este repositorio contiene el sistema de analítica actuarial interactiva y el **Asistente Conversacional Grounded (Tolerancia Cero a Alucinaciones `S0`)** para el análisis de severidad de siniestros de automóviles en las 32 entidades federativas de México (`2020–2024`).

El proyecto está organizado como un **Monolito Modular con Cuatro Foundations**, separando estrictamente el significado del dato, los cálculos matemáticos, la validación/auditoría y la interfaz conversacional:

1. **Semantic Foundation (`src/chubb/semantic_foundation/`) — *¿Qué significa el dato?***
   Catálogos de las 32 entidades federativas, resolución de alias sin traslape, registro de métricas, unidades y reglas temporales (`2020–2024`). *No ejecuta cálculos ni invoca LLMs.*
2. **Analytical Foundation (`src/chubb/analytical_foundation/`) — *¿Cómo se obtiene el resultado?***
   Motor determinista de cálculos actuariales (`ROUND_HALF_UP` sobre representación decimal más corta IEEE-754), rankings de competencia (`1, 1, 3`), referencias nacionales dinámicas, concentración Pareto, CAGR, resúmenes ejecutivos y recomendaciones basadas en datos. *Funciona al 100% sin conexión con un LLM.*
3. **Validation Foundation (`src/chubb/validation_foundation/`) — *¿Es confiable y consistente?***
   Validador de esquema e integridad referencial (`ActuarialDataValidator`), pre-validador de contratos de consulta (`QueryValidator`), validador de resultados (`ResultValidator`) y verificador post-generación con auditoría de slots semánticos (`ActuarialOutputVerifier` contra `HallucinationDetectedError` y `LabelSwapDetectedError`).
4. **Conversational AI (`src/chubb/conversational_ai/`) — *¿Cómo interactúa con el usuario?***
   Parser de lenguaje natural a representación intermedia estructurada (`QueryIR`), gestor de memoria conversacional (`ConversationMemoryManager`), síntesis narrativa grounded y conectores opcionales para proveedores LLM (`OllamaProvider`, `OpenAICompatibleProvider`).

---

## 2. Estructura del Repositorio

```text
chubb/
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── app/                            # Frontend interactivo HTML5/CSS/JS
│   ├── index.html
│   ├── css/styles.css
│   ├── js/{app.js, actuarial_engine.js}
│   └── assets/
├── src/
│   ├── chubb/
│   │   ├── semantic_foundation/    # Catálogos, entidades, métricas y periodos
│   │   ├── analytical_foundation/  # Motor actuarial determinista y repositorio
│   │   ├── validation_foundation/  # Validadores de datos, QueryIR y verificador S0
│   │   ├── conversational_ai/      # Parser NL, memoria, grounding y proveedores LLM
│   │   ├── contracts/              # Contratos explícitos (QueryIR, AnalyticalResult)
│   │   └── infrastructure/         # Resolución de rutas y JsonDataRepository
│   ├── actuarial_core.py           # Fachada de compatibilidad
│   ├── llm_grounding.py            # Fachada de compatibilidad
│   ├── ai_assistant_llm.py         # Fachada de compatibilidad
│   └── validate_assistant_outputs.py
├── config/
│   ├── semantic/{entities.json, aliases.json, metrics.json, periods.json}
│   └── business_rules/actuarial_rules.json
├── data/
│   ├── raw/{baseline_siniestros.csv, mexico_estados.geojson}
│   ├── curated/data.json
│   └── schemas/actuarial_data.schema.json
├── pipelines/{generate_json.py, build_mexico_map_svg.py}
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── golden/
│   ├── adversarial/
│   ├── parity/{generate_parity_vectors.py, test_parity.mjs}
│   ├── performance/benchmark_10k/{independent_oracle.py, run_benchmark_10k.py}
│   └── fixtures/parity_vectors.json
├── notebooks/analisis_severidad_siniestros.ipynb
├── scripts/{dev_server.py, generate_notebook.py, run_quality_gates.py}
├── output/{analysis/, benchmarks/}
└── docs/{architecture/, semantic/, methodology/, validation/}
```

---

## 3. Ejecución Local y Quality Gates

### Levantar el servidor web local (sin caché)
```bash
python3 scripts/dev_server.py 8000
# Abrir http://localhost:8000/index.html
```

### Ejecutar todos los Quality Gates automatizados (`QG-01` a `QG-08`)
```bash
python3 scripts/run_quality_gates.py
```

### Ejecutar suites individuales
```bash
# Pruebas unitarias, de integración, golden y adversariales
python3 -m unittest discover -s tests -v

# Auditoría canónica de salidas contra data.json (13/13 checks)
python3 src/validate_assistant_outputs.py

# Paridad matemática Python <-> JavaScript (35/35 vectores)
node tests/parity/test_parity.mjs

# Benchmark de 10,000 consultas contra Oráculo Independiente (0 errores S0)
python3 tests/performance/benchmark_10k/run_benchmark_10k.py
```

---

## 4. Documentación Técnica

- [Architecture Overview](docs/architecture/overview.md)
- [Dependency Rules](docs/architecture/dependency_rules.md)
- [Component Registry & Migration Mapping](docs/architecture/component_registry.md)
- [Databricks & Streamlit Migration Readiness](docs/architecture/databricks_migration.md)
- [Semantic Metric Catalog](docs/semantic/metric_catalog.md)
- [Actuarial Business Rules (`RN-01`..`RN-06`)](docs/methodology/actuarial_rules.md)
- [Quality Gates Specification](docs/validation/quality_gates.md)
- [10K Benchmark & Independent Oracle Methodology](docs/validation/benchmark_methodology.md)
