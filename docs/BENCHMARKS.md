# Benchmarks and Evidence

This document summarizes committed benchmark/gate evidence. It avoids claims that are not backed by artifacts.

## Final certification summary

Source: `artifacts/test-reports/final-certification/final-certification-summary.json`.

- `overallPass=true`
- Backend compile: `PASS`
- Dashboard typecheck: `PASS`
- Dashboard build: `PASS`
- Final solver invariant: `IRX_ML_FUSED_HYBRID`

## FAST_GATE

Source: final certification `fastGate`.

- Completed: `7/7`
- Runtime: `222516 ms`
- Late regression: `0`
- Dominance failures: `0`

FAST is a regression/smoke profile. It is not the primary quality benchmark.

## QUALITY_BENCHMARK

Source: final certification `qualityBenchmark`.

- Completed: `20/20`
- Distance objective: `20W/0T/0L`
- OR-Tools objective: `15W/5T/0L`
- Late regression: `0`
- Dominance failures: `0`

## Academic/static and PDPTW gates

- Academic static gate: CVRP and VRPTW completed.
- PDPTW gate: capacity violations `0`, pickup-before-dropoff violations `0`.

## External solver evidence

Final certification records:

- PyVRP: `COMPLETED`
- VROOM: `EVIDENCE_GAP`

This means VROOM should not be claimed as fully completed in final evidence unless a later artifact proves it.

## Live and rescue evidence

- Live stress: `pass=true`, cycles `4`, stale buffered orders `0`.
- Rescue: `pass=true`, `lateNotWorse=true`.

## Adaptive ML evidence

Source: `artifacts/test-reports/adaptive-ml-policy/v0.9.9-quality-seeking-final-summary.json`.

- Completed: `20/20`
- Improved cases: `2`
- Total distance gain: `1.6 km`
- Loss cases: `0`
- Late regressions: `0`
- Dominance failures: `0`
- Coverage regressions: `0`

## v0.9.10 ML-guided PD-LNS final gate

Source: `artifacts/test-reports/v0.9.10-ml-guided-pd-lns/final-20case/ml-hybrid-pd-lns-final-summary.json`.

- Completed: `20/20`
- Overall pass: `true`
- Best seed improved: `19/20`
- ML-guided better than heuristic: `6/20`
- Hybrid worse than AUTO: `0`
- Total distance gain over best seed: `620.4 km`
- Late regressions: `0`
- Coverage regressions: `0`
- Pickup/dropoff violations: `0`
- Capacity violations: `0`
- Dominance failures: `0`

Correct claim: ML-guided Hybrid PD-LNS improves the best available seed at pickup/dropoff sequence level in 19/20 final-gate cases, beats heuristic PD-LNS in 6/20 cases, and does not regress AUTO or hard constraints.

Caveat: total hybrid gain (`404.5 km`) does not exceed total heuristic gain (`429.7 km`) on this suite, so the evidence does not support a claim that HYBRID always or generally beats heuristic PD-LNS on aggregate distance gain.

## v0.9.10-C tri-model fusion gates

Sources:

- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/fusion-5case/tri-model-fusion-summary.json`
- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/ablation-5case/tri-model-causal-ablation-summary.json`
- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/tri-model-decision-report.json`

Fusion gate:

- Completed: `5/5`
- Forecast static calls: `0`
- Tabular / RouteFinder / GreedRL calls: `5/5` each
- Fusion worse than best single model: `0`
- Fusion better than best single model: `1/5`
- Total fusion gain: `98.3 km`
- Total best single-model gain: `96.5 km`
- Pickup/dropoff, capacity, late, coverage, dominance failures: `0`

Causal ablation:

- Verdict: `TRI_MODEL_CAUSAL_ABLATION_PROVEN`
- Model workers with contribution: `3`
- Tabular ablation loss cases: `2`
- RouteFinder ablation loss cases: `1`
- GreedRL ablation loss cases: `2`

Correct claim: Static PD-LNS safely fuses Tabular, RouteFinder, and GreedRL without Forecast. The no-regress selector prevents underperforming the best single-model candidate on the 5-case gate and proves selected fusion gain.

## API/runtime/Playground evidence

- API contract: `artifacts/test-reports/v0.9.9.4-api-contract-final/api-contract-summary.json`
- Playground: `artifacts/test-reports/v0.9.9.5-irx-playground/playground-summary.json`
- BigData-lite: `artifacts/test-reports/v0.9.9.3-bigdata-lite-api/final-bigdata-lite-api-summary.json`
- One-click: `artifacts/test-reports/v0.9.9.6-one-click-start/one-click-gate-summary.json`

## Limitations

- Benchmarks are local repository evidence, not independent third-party certification.
- FAST timing varies by machine and should be used as regression evidence.
- BigData-lite is not distributed big-data infrastructure.
- Adaptive ML claims are limited to committed gate datasets.
