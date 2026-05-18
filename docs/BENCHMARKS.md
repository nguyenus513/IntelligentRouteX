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
