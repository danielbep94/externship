# Resultados Medidos del Benchmark: 10,000 Consultas Actuariales y de Negocio (v2)

## 1. Scorecard Comparativo de Arquitecturas

| Indicador / Dimensión | Universo Evaluado | Enfoque 1: LLM Solo (`E1`/`E2` Empírico) | Enfoque 2: Motor Determinista Puro | Enfoque 3: Modelo Híbrido Grounded (Motor + Verificador Semántico) | Meta de Aceptación Justificada |
|---|---:|---:|---:|---:|---:|
| **Exactitud Numérica ($\text{Acc}_{\text{num}}$)** | 7,925 consultas con cálculo | *NO_MEDIDO (Sin ser* | **100.00 %** (7,925/7,925) | **100.00 %** (7,925/7,925) | **$\ge 99.90\%$ (`S0 = 0`)** |
| **Métricas de Negocio Correctas ($\text{Acc}_{\text{biz}}$)** | 7,925 consultas con cálculo | *NO_MEDIDO (Sin ser* | **100.00 %** (7,925/7,925) | **100.00 %** (7,925/7,925) | **$\ge 99.90\%$ (`S0 = 0`)** |
| **Exactitud sobre Familias Matemáticas Independientes ($N_{\text{indep}}$)** | 3,289 familias únicas | *NO_MEDIDO (Sin ser* | **100.00 %** (3,289/3,289) | **100.00 %** (3,289/3,289) | **100.00 % en `S0`** |
| **Consistencia en Clústeres de Paráfrasis ($\text{Cons}$)** | 280 clústeres (1,400 consultas) | *NO_MEDIDO (Sin ser* | **100.00 %** (280/280) | **100.00 %** (280/280) | **$\ge 99.00\%$** |
| **Trazabilidad Completa ($\text{Trace}$: Fuente, Corte, Filtros, Op)** | 10,000 consultas | *NO_MEDIDO (Sin ser* | **100.00 %** (10,000/10,000) | **100.00 %** (10,000/10,000) | **100.00 %** |
| **Confiabilidad ($\text{Rel}$: Abstención en Ventas/Rentabilidad/Faltantes)** | 2,075 consultas sin dato | *NO_MEDIDO (Sin ser* | **100.00 %** (2,075/2,075) | **100.00 %** (2,075/2,075) | **100.00 % (`S0 = 0`)** |
| **Errores Críticos `S0` (Alucinación, Label Swap, Signo, Categoría)** | 10,000 consultas | *NO_MEDIDO (Sin ser* | **0** | **0** | **0 (Tolerancia Cero)** |
| **Tiempo Medio de Respuesta (Pipeline en Memoria)** | 10,000 consultas | *Depende de GPU/API* | **1.340 ms** | **1.340 ms** (+ inferencia LLM si activo) | Documentado |

> **Nota Metodológica (Problema 6)**: La columna *Enfoque 1: LLM Solo* no se rellena con simulaciones sintéticas. Cuando se ejecuta en un entorno sin servidor LLM activo, se reporta como `NO_MEDIDO` y puede ejecutarse empíricamente pasando `--ollama-model llama3:8b` tanto en modo `E1` (paridad estricta de registros) como `E2` (arquitectura integral).

---

## 2. Desglose por Categoría (`C1`–`C8`) y Severidad de Errores (`S0`–`S2`)

| Categoría | Total Consultas | Aprobadas Integralmente | Errores `S0` (Críticos) | Errores `S1` (Mayores) | Errores `S2` (Menores) | Tasa de Éxito |
|---|---:|---:|---:|---:|---:|---:|
| `C1_SINGLE_STATE` | 1,800 | 1,800 | **0** | 0 | 0 | **100.00 %** |
| `C2_MULTI_COMPARISON` | 1,600 | 1,600 | **0** | 0 | 0 | **100.00 %** |
| `C3_EXECUTIVE_SUMMARY` | 1,500 | 1,500 | **0** | 0 | 0 | **100.00 %** |
| `C4_RANKINGS_PARETO_CAGR_R2` | 1,100 | 1,100 | **0** | 0 | 0 | **100.00 %** |
| `C5_CONSISTENCY_CLUSTER` | 1,400 | 1,400 | **0** | 0 | 0 | **100.00 %** |
| `C6_MISSING_BUSINESS_KPIS` | 1,200 | 1,200 | **0** | 0 | 0 | **100.00 %** |
| `C7_OUT_OF_RANGE_AND_GRANULARITY` | 800 | 800 | **0** | 0 | 0 | **100.00 %** |
| `C8_UNSEEN_BUSINESS_AND_RULES` | 600 | 600 | **0** | 0 | 0 | **100.00 %** |

---

## 3. Desglose por Nivel de Dificultad Matemática (`M0`–`M4`, Problema 3)

| Nivel Matemático | Consultas Evaluadas | Aprobadas | Exactitud (%) |
|---|---:|---:|---:|
| `M0_abstencion` | 2,075 | 2,075 | **100.00 %** |
| `M1_lectura_directa` | 375 | 375 | **100.00 %** |
| `M2_aritmetica_bivariada` | 2,525 | 2,525 | **100.00 %** |
| `M3_agregacion_ranking_nacional` | 2,115 | 2,115 | **100.00 %** |
| `M4_compuesta_multianual` | 2,910 | 2,910 | **100.00 %** |

---

## 4. Auditoría de Sensibilidad del Verificador por Inyección de Fallos (Problema 4 y Problema 6)

Esta tabla evalúa exclusivamente la **sensibilidad del verificador (`ActuarialOutputVerifier` + `evaluate_single_response`)** inyectando 600 mutaciones controladas sobre respuestas reales:

| Tipo de Mutación Inyectada | Severidad Esperada | Fallos Inyectados | Fallos Detectados por el Verificador | Recall de Detección |
|---|---|---:|---:|---:|
| `LABEL_SWAP_S0` | **S0 (Crítico)** | 100 | 100 | **100.0 %** |
| `HALLUCINATED_NUMBER_S0` | **S0 (Crítico)** | 100 | 100 | **100.0 %** |
| `SILENT_KPI_SUBSTITUTION_S0` | **S0 (Crítico)** | 100 | 100 | **100.0 %** |
| `CATEGORY_INVERSION_S0` | **S0 (Crítico)** | 100 | 100 | **100.0 %** |
| `NUMERIC_DRIFT_S1` | **S1 (Mayor)** | 100 | 100 | **100.0 %** |
| `MISSING_TRACE_S2` | **S2 (Menor)** | 100 | 100 | **100.0 %** |
| **TOTAL AUDITORÍA DEL VERIFICADOR** | **`S0`–`S2`** | **600** | **600** | **100.0 %** |
