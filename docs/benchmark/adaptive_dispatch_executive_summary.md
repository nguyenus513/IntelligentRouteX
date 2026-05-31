# Adaptive Dispatch Executive Benchmark Summary

## Positioning

Static routing and live rolling dispatch measure different capabilities.

- Static routing: all orders are known upfront; metric focus is vehicle count and distance.
- Live rolling dispatch: orders arrive continuously; drivers move; metric focus is served orders, late orders, waiting time, bundle rate, utilization, and route stability.

Recommended claim:

> In static routing, IRX is competitive with OR-Tools/PyVRP and still trails VROOM on selected Li-Lim cases. In synthetic live rolling dispatch, the Adaptive Bundle Dispatch Layer outperforms Greedy, OR-Tools rolling, VROOM rolling, and PyVRP rolling on dispatch KPIs.

Do not claim IRX always beats VROOM. The current evidence supports live rolling dispatch KPI dominance, not universal static routing dominance.

## Static Routing Result

Artifacts:

- `artifacts/benchmark/official_solomon_lilim_fast_rerun_20260531/phase15_large_benchmark_report.md`
- `artifacts/benchmark/vroom_lilim_fast_rerun_20260531/aggregate_summary.md`
- `artifacts/benchmark/pyvrp_solomon_fast_scaled_20260531/pyvrp_solomon_fast_scaled_results.json`

| Comparison | Scope | Result |
|---|---|---|
| IRX vs OR-Tools | Solomon + Li-Lim fast | `1W / 5T / 0L`, `-0.096%` distance, `-1` vehicle |
| IRX vs VROOM | Li-Lim LC/LR/LRC101 | `0W / 1T / 2L`, `+2.28%` distance, `+2` vehicles |
| IRX vs PyVRP | Solomon C/R/RC101 | `2W / 0T / 1L`, `+0.011%` distance, `-3` vehicles |

Interpretation: IRX is clean and competitive in static smoke tests, but VROOM remains stronger on Li-Lim LR/LRC static routing.

## Live Rolling Dispatch Result

Artifact:

- `artifacts/benchmark/adaptive_bundle_dispatch_live_rolling_3seed_20260531/adaptive_bundle_dispatch_benchmark.md`

Protocol:

- Scenarios: normal streaming, rush-hour burst, dense city, sparse orders, driver delay, tight deadlines, capacity pressure, stress.
- Seeds: `1,2,3`.
- Baselines: Greedy nearest, solver-only rolling, OR-Tools rolling, VROOM rolling, PyVRP rolling, ablations A1-A5, full Adaptive A6.

| Comparison | Served | Late | Avg wait | Bundle | Utilization | Distance | Runtime p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full Adaptive vs Greedy | `+1614` | `-62.8%` | `-59.0%` | `+33.0 pp` | `+23.1 pp` | `-23.2%` | `+158 ms` |
| Full Adaptive vs Solver-only | `+826` | `-59.5%` | `-54.5%` | `+17.0 pp` | `+13.0 pp` | `-13.2%` | `+84 ms` |
| Full Adaptive vs OR-Tools rolling | `+630` | `-57.7%` | `-52.9%` | `+14.0 pp` | `+10.8 pp` | `-9.5%` | `+60 ms` |
| Full Adaptive vs VROOM rolling | `+532` | `-56.1%` | `-53.5%` | `+12.0 pp` | `+9.6 pp` | `-5.5%` | `+70 ms` |
| Full Adaptive vs PyVRP rolling | `+630` | `-57.0%` | `-53.5%` | `+13.0 pp` | `+10.7 pp` | `-6.6%` | `+38 ms` |

Mean +/- std across seeds for selected baselines:

| Baseline | Late | Avg wait | Bundle rate | Utilization | Distance |
|---|---:|---:|---:|---:|---:|
| VROOM rolling | `500.667 +/- 2.309` | `9.203 +/- 0.033` | `0.437 +/- 0.001` | `0.793 +/- 0.001` | `3721.597 +/- 6.167` |
| OR-Tools rolling | `519.000 +/- 3.606` | `9.099 +/- 0.033` | `0.417 +/- 0.001` | `0.781 +/- 0.001` | `3885.062 +/- 6.448` |
| PyVRP rolling | `511.333 +/- 3.055` | `9.203 +/- 0.033` | `0.427 +/- 0.001` | `0.782 +/- 0.001` | `3763.659 +/- 6.243` |
| Full Adaptive | `219.667 +/- 1.528` | `4.284 +/- 0.016` | `0.556 +/- 0.001` | `0.889 +/- 0.001` | `3515.602 +/- 5.760` |

## Why Results Differ

VROOM is strong on static route optimization when the full order set is known. Full Adaptive is stronger in live rolling dispatch because it controls:

- order admission and aging-regret priority;
- bundle candidate scoring;
- driver-bundle matching;
- convenient insertion behind frozen stops;
- break-risk detection;
- destroy-repair before committing routes.

## Current Evidence Level

This is a reproducible synthetic deterministic benchmark with 3 seeds. It is strong enough for engineering and report evidence. For paper-grade claims, add public live dispatch datasets, real traffic replay, and more seeds with significance tests.
