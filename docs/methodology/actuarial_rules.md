# Actuarial Business Rules (`RN-01` to `RN-06`)

All actuarial rules are governed by the single source of truth in `config/business_rules/actuarial_rules.json` and executed identically in Python (`chubb.analytical_foundation`) and JavaScript (`app/js/actuarial_engine.js`).

1. **RN-01 · National Reference & Relative Severity Index (`pts`)**:
   - `Media_ref(Y)` is the simple mean of the `n(Y)` entities with valid severity (`> 0`) in year `Y`.
   - `Índice_e(Y) = 100 × Severidad_e(Y) / Media_ref(Y)` (Base 100, formatted to 1 decimal place).
2. **RN-02 · Nominal Severity Category Thresholds**:
   - **Crítica**: `Severidad >= $11,000.00 MXN`
   - **Media**: `$7,500.00 MXN <= Severidad < $11,000.00 MXN`
   - **Baja**: `0 < Severidad < $7,500.00 MXN`
   - Evaluated on unrounded values. Annual category (`yearly_categoria[Y]`) is never substituted by the multi-year period category.
3. **RN-03 · Severity (`$/Claim`) vs. Total Cost (`MDP`) & Exposure Guardrail**:
   - `Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000`.
   - Registered vehicles (`INEGI VMRC`) measure macro fleet scale and do **not** equal insured exposure (active policies).
4. **RN-04 · Temporal Evolution (`2020 → YYYY`) & CAGR**:
   - `Var % = ((Valor_Y / Valor_2020) - 1) × 100`
   - `Δ Índice (pts) = Índice_Y - Índice_2020` (arithmetic difference in points).
5. **RN-05 · Competition Rankings (`1, 1, 3`)**:
   - Entities are ranked over `n_métrica(Y)` valid observations comparing values rounded to 2 decimal places (`ROUND_HALF_UP`).
6. **RN-06 · Deterministic `ROUND_HALF_UP` & Default Year (`2024`)**:
   - Both Python and JavaScript convert IEEE-754 floats to their shortest decimal representation and apply `ROUND_HALF_UP` (half away from zero), normalizing `-0.00` to `0.00`.
   - When the year is omitted in an executive summary query, `2024` is used by default with an explicit notice, except in continuation queries (`¿Y ...?`, `también`, `mismo año`) which inherit `confirmed_year` from memory.

