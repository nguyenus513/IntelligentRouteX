# IRX Benchmark Standard

Version: `v1.0.2.1-irx-benchmark-standard`

This benchmark standard separates runtime certification from quality claims.

## Solver rows

Each static dataset should report distinct rows:

- `GREEDY_BASELINE`
- `VROOM`
- `ORTOOLS`
- `PYVRP`
- `BEST_EXTERNAL`
- `IRX_NATIVE`
- `IRX_HYBRID_FINAL`
- `IRX_IMPROVED_EXTERNAL`

## Objective comparator

Static objective order:

1. coverage higher
2. hard violations lower
3. late count lower
4. total lateness lower
5. vehicle/route count lower
6. distance lower
7. runtime lower

CVRP emphasizes capacity feasibility, fleet size, distance, and runtime. VRPTW/PDPTW emphasizes hard feasibility, lateness/time warp, fleet size, distance, and runtime.

## Claim rules

Static PASS means `IRX_HYBRID_FINAL` has zero loss versus `BEST_EXTERNAL` under the unified comparator.
Static WIN means `IRX_IMPROVED_EXTERNAL` improves the best external seed without hard violations.
Dynamic PASS means rolling dispatch safety holds.
Dynamic WIN requires measured latency/churn/SLA gains over re-run baselines.
ML PASS means no regression versus no-ML baseline.
ML WIN requires measured quality/runtime/search gain.

Hypotheses about 3x-10x latency, 50% churn reduction, or SLA gain must remain hypotheses until measured by dynamic gates.
