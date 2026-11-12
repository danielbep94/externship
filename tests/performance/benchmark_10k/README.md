# 10K Actuarial Validation Benchmark (`tests/performance/benchmark_10k/`)

Executes 10,000 actuarial and business queries against an independent mathematical oracle (`independent_oracle.py`) using `fractions.Fraction` and `decimal.Decimal`, auditing:

1. **Experiment E1 (Strict Data Parity)** vs. **Experiment E2 (Full Architecture)**.
2. **Independent Oracle (`GOLDEN_MANUAL_CASES`)** with zero imports from `src/`.
3. **Structured Metric Contract & Semantic Slot Binding (`LABEL_SWAP_ERROR` — Severity S0)**.
4. **Adversarial & Out-of-Scope Abstention (`insufficient_data_kpi`, `unsupported_granularity`)**.

## Execution

```bash
python3 tests/performance/benchmark_10k/run_benchmark_10k.py
```

