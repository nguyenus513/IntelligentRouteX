# Industry-Grade Dispatch Benchmark

## Purpose

This benchmark evaluates live rolling dispatch quality, not static VRP route quality. It complements Solomon/Li-Lim/Homberger static routing benchmarks by measuring operational KPIs under continuous order arrival and driver motion.

## Protocol

Run:

```powershell
py -3 scripts/run_industry_grade_dispatch_benchmark.py --seeds 1,2,3,4,5 --output-dir artifacts/benchmark/industry_grade_dispatch_benchmark_20260531
```

Protocol:

- Scenarios: `normal_streaming`, `rush_hour_burst`, `dense_city`, `sparse_orders`, `driver_delay_shock`.
- Seeds: `1,2,3,4,5`.
- Baselines: `greedy_nearest`, `ortools_rolling`, `vroom_rolling`, `pyvrp_rolling`, `full_adaptive`.
- Constraint safety: pickup/dropoff precedence, capacity, frozen stop, coverage loss, and hard violations.

## Main KPI Table

Artifact: `artifacts/benchmark/industry_grade_dispatch_benchmark_20260531/industry_grade_dispatch_benchmark.md`.

| Metric | Greedy | OR-Tools Rolling | VROOM Rolling | PyVRP Rolling | Full Adaptive |
|---|---:|---:|---:|---:|---:|
| Served orders | `7735` | `8667` | `8758` | `8667` | `9254` |
| On-time rate | `0.790` | `0.835` | `0.844` | `0.838` | `0.937` |
| Late count | `1676` | `1472` | `1420` | `1453` | `587` |
| Avg wait | `9.849` | `8.569` | `8.667` | `8.667` | `4.055` |
| P95 wait | `20.595` | `17.918` | `18.124` | `18.124` | `8.407` |
| Bundle rate | `0.248` | `0.438` | `0.458` | `0.448` | `0.578` |
| Utilization | `0.667` | `0.790` | `0.801` | `0.791` | `0.897` |
| Distance/order | `1.705` | `1.291` | `1.224` | `1.251` | `1.096` |
| Runtime p95 ms | `249` | `339` | `329` | `359` | `404` |
| Violations | `0` | `0` | `0` | `0` | `0` |

## Mean +/- Std Across Seeds

| Baseline | Served | On-time | Late | Avg wait | Bundle | Utilization | Distance/order |
|---|---:|---:|---:|---:|---:|---:|---:|
| greedy_nearest | `1547.000 +/- 10.149` | `0.790 +/- 0.002` | `335.200 +/- 2.168` | `9.849 +/- 0.040` | `0.248 +/- 0.001` | `0.667 +/- 0.001` | `1.705 +/- 0.012` |
| ortools_rolling | `1733.400 +/- 11.059` | `0.835 +/- 0.003` | `294.400 +/- 3.050` | `8.569 +/- 0.034` | `0.438 +/- 0.001` | `0.790 +/- 0.001` | `1.291 +/- 0.008` |
| vroom_rolling | `1751.600 +/- 11.036` | `0.844 +/- 0.002` | `284.000 +/- 2.449` | `8.667 +/- 0.035` | `0.458 +/- 0.001` | `0.802 +/- 0.001` | `1.224 +/- 0.007` |
| pyvrp_rolling | `1733.400 +/- 11.059` | `0.838 +/- 0.003` | `290.600 +/- 2.881` | `8.667 +/- 0.035` | `0.448 +/- 0.001` | `0.791 +/- 0.001` | `1.251 +/- 0.008` |
| full_adaptive | `1850.800 +/- 5.630` | `0.937 +/- 0.001` | `117.400 +/- 0.548` | `4.055 +/- 0.017` | `0.578 +/- 0.001` | `0.897 +/- 0.001` | `1.096 +/- 0.005` |

## Full Adaptive Improvement

| Reference | Served delta | On-time lift | Late reduction | Wait reduction | Bundle lift | Util lift | Cost/order reduction |
|---|---:|---:|---:|---:|---:|---:|---:|
| greedy_nearest | `+1519` | `+14.7 pp` | `-65.0%` | `-58.8%` | `+33.0 pp` | `+23.0 pp` | `-35.7%` |
| ortools_rolling | `+587` | `+10.2 pp` | `-60.1%` | `-52.7%` | `+14.0 pp` | `+10.7 pp` | `-15.1%` |
| vroom_rolling | `+496` | `+9.3 pp` | `-58.7%` | `-53.2%` | `+12.0 pp` | `+9.6 pp` | `-10.5%` |
| pyvrp_rolling | `+587` | `+9.9 pp` | `-59.6%` | `-53.2%` | `+13.0 pp` | `+10.6 pp` | `-12.4%` |

## Constraint Safety

| Constraint | Value |
|---|---:|
| pickupDropoffViolation | `0` |
| capacityViolation | `0` |
| frozenStopViolation | `0` |
| coverageLoss | `0` |
| hardViolations | `0` |

## Claim Boundary

Supported claim:

> On synthetic live rolling dispatch benchmarks with five seeds, Full Adaptive improves served orders, on-time rate, late orders, waiting time, bundle rate, utilization, and cost/order versus Greedy, OR-Tools rolling, VROOM rolling, and PyVRP rolling.

Not supported by this benchmark alone:

- IRX is the best static VRP solver.
- IRX always beats VROOM.
- Deep learning fully replaces combinatorial optimization.

Static routing claims must continue to use Solomon, Li-Lim, Homberger, OR-Tools, VROOM, and PyVRP reports separately.
