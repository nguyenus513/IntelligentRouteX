# Adversarial Live Dispatch Benchmark

## Purpose

This is a breaking benchmark. It intentionally stresses the dispatch system to expose weak points rather than to produce a clean demo.

## Protocol

Run:

```powershell
py -3 scripts/run_adversarial_live_dispatch_benchmark.py --seeds 1,2,3,4,5 --output-dir artifacts/benchmark/adversarial_live_dispatch_20260531
```

Stress profile:

- 90-minute live simulation.
- Minutes `0-20`: normal demand.
- Minutes `20-35`: demand burst at `4x`.
- Minutes `35-90`: normal demand.
- `15%` sparse pickup/dropoff outliers.
- `30%` tight-deadline orders.
- `20%` drivers delayed with `40%` speed drop after assignment.
- `50%` drivers under capacity pressure.

Baselines:

- `greedy_nearest`
- `ortools_rolling`
- `vroom_rolling`
- `pyvrp_rolling`
- `full_adaptive`

## VROOM Rolling vs Full Adaptive

Artifact: `artifacts/benchmark/adversarial_live_dispatch_20260531/adversarial_live_dispatch_benchmark.md`.

| Metric | VROOM Rolling | Full Adaptive | Verdict |
|---|---:|---:|---|
| Late count | `1714` | `856` | `WIN` |
| P95 wait | `73.860` | `44.316` | `WIN` |
| Max order age | `142.918` | `85.752` | `WIN` |
| Repair success | `0.000` | `0.693` | `INFO` |
| Route churn | `0.230` | `0.143` | `WIN` |
| Runtime p99 | `931` | `2576` | `COST` |
| Violations | `0` | `0` | `WIN` |

## All Baselines

| Baseline | Served | Late | P95 late | P99 late | Avg wait | P95 wait | Max age | Bundle | Bad bundle | Repair success | Churn | Runtime p99 | Violations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| greedy_nearest | `2849` | `1532` | `53.474` | `79.891` | `35.721` | `81.229` | `185.607` | `0.040` | `0.380` | `0.000` | `0.331` | `673` | `30` |
| ortools_rolling | `3739` | `1757` | `50.692` | `75.734` | `32.468` | `73.833` | `142.867` | `0.254` | `0.344` | `0.000` | `0.239` | `967` | `0` |
| vroom_rolling | `3829` | `1714` | `49.419` | `73.831` | `32.480` | `73.860` | `142.918` | `0.273` | `0.328` | `0.000` | `0.230` | `931` | `0` |
| pyvrp_rolling | `3757` | `1734` | `50.588` | `75.577` | `32.615` | `74.167` | `143.514` | `0.263` | `0.338` | `0.000` | `0.235` | `1032` | `0` |
| full_adaptive | `4296` | `856` | `23.160` | `34.601` | `19.488` | `44.316` | `85.752` | `0.431` | `0.027` | `0.693` | `0.143` | `2576` | `0` |

## Mean +/- Std Across Seeds

| Baseline | Late | P95 wait | Max age | Bad bundle | Repair success | Runtime p99 |
|---|---:|---:|---:|---:|---:|---:|
| greedy_nearest | `306.400 +/- 7.701` | `81.229 +/- 1.971` | `185.607 +/- 4.505` | `0.380 +/- 0.003` | `0.000 +/- 0.000` | `673.200 +/- 8.167` |
| ortools_rolling | `351.400 +/- 3.782` | `73.833 +/- 0.482` | `142.867 +/- 0.934` | `0.344 +/- 0.003` | `0.000 +/- 0.000` | `966.800 +/- 3.962` |
| vroom_rolling | `342.800 +/- 5.070` | `73.860 +/- 0.487` | `142.918 +/- 0.942` | `0.328 +/- 0.002` | `0.000 +/- 0.000` | `930.600 +/- 3.647` |
| pyvrp_rolling | `346.800 +/- 4.266` | `74.167 +/- 0.487` | `143.514 +/- 0.942` | `0.338 +/- 0.003` | `0.000 +/- 0.000` | `1032.000 +/- 4.123` |
| full_adaptive | `171.200 +/- 2.387` | `44.316 +/- 0.294` | `85.752 +/- 0.570` | `0.027 +/- 0.000` | `0.693 +/- 0.000` | `2576.200 +/- 10.281` |

## Failure Diagnosis

Full Adaptive still exposes three adversarial weaknesses:

| Diagnosis | Count | Suggested optimization |
|---|---:|---|
| `order-admission-aging-too-weak` | `5` | increase nonlinear age score; add hard max-wait admission rule |
| `convenient-insertion-needs-deadline-safety` | `5` | require zero extra lateness; add churn/deadline safety guard |
| `runtime-p99-too-high` | `5` | cap top-K orders, beam width, repair budget; early stop feasible improvement |

## Interpretation

Full Adaptive remains better than VROOM rolling on late count, wait tail, max order age, bad bundle rate, route churn, and violations under adversarial load. The cost is runtime tail: `runtimeP99 = 2576 ms`, much higher than VROOM rolling at `931 ms`.

This benchmark identifies the next optimization priorities:

1. hard max-wait admission rule;
2. stricter convenient insertion deadline safety;
3. repair/candidate time budget caps to reduce runtime p99.

## Post-Optimization Rerun

Artifact: `artifacts/benchmark/adversarial_live_dispatch_after_budget_20260531/adversarial_live_dispatch_benchmark.md`.

Applied fixes:

- runtime budget caps for candidate/repair path;
- nonlinear aging and forced old-order priority;
- deadline-safe convenient insertion filters;
- bounded repair budget and candidate caps.

| Metric | Before | After | Target | Result |
|---|---:|---:|---:|---|
| Runtime p99 | `2576 ms` | `1443 ms` | `<1500 ms` | PASS |
| Max order age | `85.752` | `53.166` | `<60` | PASS |
| Late count | `856` | `667` | no >5% regression | PASS |
| P95 wait | `44.316` | `44.316` | hold or reduce | PASS |
| Bundle rate | `0.431` | `0.431` | no large drop | PASS |
| Violations | `0` | `0` | `0` | PASS |

Post-optimization diagnosis:

| Diagnosis | Count |
|---|---:|
| `no-critical-breakage-detected` | `5/5 seeds` |

Result: the three original bottlenecks are cleared under this adversarial benchmark. Runtime p99 remains higher than VROOM, but it now fits the target tail budget while preserving dispatch KPI wins.
