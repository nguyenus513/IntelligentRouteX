# Adaptive Bundle Ablation Report

## Purpose

This benchmark proves the algorithmic contribution of each Adaptive Bundle Dispatch module. It is separate from static solver benchmarks and from the multi-baseline industry benchmark.

## Protocol

Run:

```powershell
py -3 scripts/run_adaptive_bundle_ablation_benchmark.py --seeds 1,2,3,4,5 --output-dir artifacts/benchmark/adaptive_bundle_ablation_benchmark_20260531
```

Protocol:

- Scenarios: `normal_streaming`, `rush_hour_burst`, `dense_city`, `sparse_orders`, `driver_delay_shock`.
- Seeds: `1,2,3,4,5`.
- Configs: `A0_baseline` through `A6_full_adaptive`.
- Metrics: served orders, late count, average wait, bundle rate, utilization, distance, runtime p50/p95/p99/max, safety violations.

## Main Ablation Table

| Config | Served | Late | Avg wait | Bundle | Utilization | Distance | Runtime p95 | Violations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A0_baseline | `8478` | `1537` | `8.864` | `0.408` | `0.768` | `11392.098` | `632` | `0` |
| A1_order_priority | `8667` | `1420` | `8.076` | `0.428` | `0.789` | `11153.795` | `620` | `0` |
| A2_bundle_scoring | `8758` | `1372` | `7.879` | `0.488` | `0.813` | `10886.833` | `630` | `0` |
| A3_driver_matching | `8850` | `1322` | `7.584` | `0.498` | `0.844` | `10768.505` | `645` | `0` |
| A4_convenient_insertion | `9036` | `978` | `5.040` | `0.528` | `0.856` | `10364.665` | `668` | `0` |
| A5_destroy_repair | `9126` | `747` | `4.745` | `0.538` | `0.867` | `10235.102` | `858` | `0` |
| A6_full_adaptive | `9254` | `587` | `4.055` | `0.578` | `0.897` | `9874.778` | `875` | `0` |

## Incremental Contribution

| Step | Served | Late reduction | Wait reduction | Bundle lift | Util lift | Distance reduction | Runtime p95 delta | Late regression |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A0 -> A1 Order Priority | `+189` | `+7.6%` | `+8.9%` | `+2.0 pp` | `+2.1 pp` | `+2.1%` | `-12 ms` | `0` |
| A1 -> A2 Bundle Scoring | `+91` | `+3.4%` | `+2.4%` | `+6.0 pp` | `+2.4 pp` | `+2.4%` | `+10 ms` | `0` |
| A2 -> A3 Driver Matching | `+92` | `+3.6%` | `+3.7%` | `+1.0 pp` | `+3.1 pp` | `+1.1%` | `+15 ms` | `0` |
| A3 -> A4 Convenient Insertion | `+186` | `+26.0%` | `+33.5%` | `+3.0 pp` | `+1.2 pp` | `+3.8%` | `+23 ms` | `0` |
| A4 -> A5 Destroy-Repair | `+90` | `+23.6%` | `+5.9%` | `+1.0 pp` | `+1.1 pp` | `+1.2%` | `+190 ms` | `0` |
| A5 -> A6 Full Adaptive | `+128` | `+21.4%` | `+14.5%` | `+4.0 pp` | `+3.0 pp` | `+3.5%` | `+17 ms` | `0` |

## A0 to A6 Summary

| Metric | Improvement |
|---|---:|
| Served orders | `+776` |
| Late reduction | `+61.8%` |
| Avg wait reduction | `+54.3%` |
| Bundle rate lift | `+17.0 pp` |
| Utilization lift | `+12.9 pp` |
| Distance reduction | `+13.3%` |
| Runtime p95 delta | `+243 ms` |

## Runtime Budget

| Config | P50 | P95 | P99 | Max |
|---|---:|---:|---:|---:|
| A0_baseline | `174` | `632` | `720` | `721` |
| A1_order_priority | `172` | `620` | `707` | `708` |
| A2_bundle_scoring | `174` | `630` | `718` | `719` |
| A3_driver_matching | `175` | `645` | `735` | `736` |
| A4_convenient_insertion | `179` | `668` | `762` | `763` |
| A5_destroy_repair | `223` | `858` | `978` | `979` |
| A6_full_adaptive | `227` | `875` | `997` | `1000` |

## Safety Report

| Safety metric | Value |
|---|---:|
| pickupDropoffViolations | `0` |
| capacityViolations | `0` |
| frozenStopViolations | `0` |
| coverageLoss | `0` |
| hardViolations | `0` |
| lateRegression | `0` |

## Mean +/- Std Across Seeds

| Config | Served | Late | Avg wait | Bundle | Utilization | Distance | Runtime p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A0_baseline | `1695.600 +/- 10.807` | `307.400 +/- 1.949` | `8.864 +/- 0.036` | `0.408 +/- 0.001` | `0.768 +/- 0.001` | `2278.420 +/- 6.028` | `629.800 +/- 2.588` |
| A1_order_priority | `1733.400 +/- 11.059` | `284.000 +/- 2.449` | `8.076 +/- 0.032` | `0.428 +/- 0.001` | `0.789 +/- 0.001` | `2230.759 +/- 5.891` | `618.200 +/- 2.588` |
| A2_bundle_scoring | `1751.600 +/- 11.036` | `274.400 +/- 2.608` | `7.879 +/- 0.032` | `0.488 +/- 0.001` | `0.814 +/- 0.001` | `2177.367 +/- 5.719` | `629.000 +/- 1.581` |
| A3_driver_matching | `1770.000 +/- 11.895` | `264.400 +/- 2.074` | `7.584 +/- 0.031` | `0.498 +/- 0.001` | `0.844 +/- 0.001` | `2153.701 +/- 5.652` | `644.000 +/- 1.581` |
| A4_convenient_insertion | `1807.200 +/- 12.518` | `195.600 +/- 1.673` | `5.040 +/- 0.021` | `0.528 +/- 0.001` | `0.856 +/- 0.002` | `2072.933 +/- 5.419` | `667.000 +/- 1.581` |
| A5_destroy_repair | `1825.200 +/- 11.967` | `149.400 +/- 1.140` | `4.745 +/- 0.020` | `0.538 +/- 0.001` | `0.867 +/- 0.001` | `2047.020 +/- 5.348` | `855.800 +/- 2.588` |
| A6_full_adaptive | `1850.800 +/- 5.630` | `117.400 +/- 0.548` | `4.055 +/- 0.017` | `0.578 +/- 0.001` | `0.897 +/- 0.001` | `1974.956 +/- 5.140` | `874.400 +/- 2.302` |

## Conclusion

Ablation study shows each module contributes measurable improvement. Convenient Insertion and Destroy-Repair create the largest late/wait gains. Full Adaptive gives the best combined served orders, late count, waiting time, bundle rate, utilization, and distance, while preserving zero constraint regressions.
