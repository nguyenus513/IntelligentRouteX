# IRX Benchmark Standard Report

Generated for `v1.0.2.1-irx-benchmark-standard`.

## Benchmark philosophy
Runtime certification and quality claims are separated. No latency/churn/SLA improvement is claimed without measured dynamic evidence.

## Dataset taxonomy
Static suite uses synthetic/benchmark-backed CVRP, VRPTW, PDPTW-style cases represented by the current all-in-one compare datasets.

## Solver baselines
Baselines are VROOM, OR-Tools, PyVRP readiness, greedy/native rows, and IRX hybrid final.

## Objective comparator
Coverage, hard violations, late count, total lateness, fleet/route count, distance, runtime.

## Static suite result
See `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard/static/final-summary.json`.

## Dynamic suite result
See `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard/dynamic/final-summary.json`. Dynamic win hypotheses remain unclaimed unless measured against re-run baselines.

## ML contribution result
See `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard/ml/final-summary.json`.

## Limitations
The dynamic benchmark currently validates safety and cycle runtime smoke behavior; it does not yet prove churn/latency/SLA win against VROOM/OR-Tools/PyVRP re-run baselines.

## Claims allowed
Only claims present in final summary `allowedClaims` are allowed.

## Next work
Add fair dynamic re-run baselines with identical freeze constraints and measure decision latency, route churn, and on-time rate.
