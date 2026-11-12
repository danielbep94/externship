# 10K Benchmark & Independent Oracle Methodology

## 1. Experimental Design (`E1` vs `E2`)

- **Experiment E1 (Strict Data Parity)**: Evaluates supported queries (`C1`–`C4`, `C6`, `C8`) where `data.json` contains complete observations, measuring pure mathematical and semantic slot accuracy.
- **Experiment E2 (End-to-End Architecture & Guardrails)**: Evaluates all 10,000 queries including missing data/year-2020 base edge cases (`C5`) and adversarial/unsupported KPI or sub-state/sub-annual granularity queries (`C7`).

## 2. Independent Oracle (`independent_oracle.py`)

- Implements all actuarial formulas from scratch using `fractions.Fraction` and `decimal.Decimal` without importing any module from `src/`.
- Self-audits against `GOLDEN_MANUAL_CASES` before scoring any benchmark query.

## 3. Error Severity Taxonomy (`S0`–`S3`)

- **S0 (Critical — Zero Tolerance)**: Hallucinated number (`HallucinationDetectedError`), semantic label swap (`LabelSwapDetectedError`), annual/period category leak, or failure to abstain on unsupported KPIs/granularities.
- **S1 (Major)**: Intent routing mismatch or incomplete table section.
- **S2 (Minor)**: Missing interpretation note on default year or duplicate alias mention.
- **S3 (Cosmetic)**: Minor formatting or whitespace variation.

