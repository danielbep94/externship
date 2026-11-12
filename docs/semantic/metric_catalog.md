# Semantic Metric Catalog (`config/semantic/metrics.json`)

| Metric ID (`canonical`) | Display Label | Official Unit | Precision | Business Rule |
|---|---|---|---|---|
| `severidad` | Severidad Unitaria ($/Siniestro) | `MXN por siniestro` | 2 decimals | `RN-03`: `(MDP × 1,000,000) / (0.35 × 0.30 × población_2020)` |
| `costo_mdp` | Costo Total de Siniestros (MDP) | `MDP (Millones de Pesos)` | 2 decimals | `RN-03`: Aggregate claims cost in millions of MXN (`1 MDP = $1,000,000 MXN`) |
| `indice_relativo` | Índice Relativo de Severidad | `pts (Base Nacional = 100)` | 1 decimal | `RN-01`: `100 × Severidad_e(Y) / Media_ref(Y)` |
| `riesgo_categoria` | Categoría y Nivel de Riesgo | `Estrato (Baja, Media, Crítica)` | Categorical | `RN-02`: Crítica $\ge \$11,000$; Media $[\$7,500, \$11,000)$; Baja $< \$7,500$ MXN |
| `crecimiento_cagr` | Crecimiento Histórico y CAGR | `% acumulado / % anual compuesto` | 1 decimal | `RN-04`: Cumulative 2020–2024 % and 4-year compound annual rate |
| `pareto` | Concentración de Pérdida (Pareto) | `% del total nacional` | 1 decimal | `RN-03`: Top-K share of national aggregate MDP |
| `asociacion_precios` | Correlación y Regresión (Scatter R²) | `r de Pearson / R² score` | 4 / 2 decimals | `OLS-Scatter`: Linear association with vehicle commercial price |

