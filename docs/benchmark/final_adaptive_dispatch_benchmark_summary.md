# Final Adaptive Dispatch Benchmark Summary

## Executive Positioning

IRX should be presented as a hybrid routing and live dispatch system:

- Static solver portfolio: competitive with OR-Tools/PyVRP, still behind VROOM on selected Li-Lim static cases.
- Adaptive Bundle Dispatch Layer: stronger on live rolling dispatch KPIs where orders arrive continuously and drivers are already moving.
- ML role: learning-assisted scoring and policy signals, not a claim that deep learning replaces optimization.

## 1. Static Solver Benchmark

Artifacts:

- `artifacts/benchmark/official_solomon_lilim_fast_rerun_20260531/phase15_large_benchmark_report.md`
- `artifacts/benchmark/vroom_lilim_fast_rerun_20260531/aggregate_summary.md`
- `artifacts/benchmark/pyvrp_solomon_fast_scaled_20260531/pyvrp_solomon_fast_scaled_results.json`

| Comparison | Scope | Result |
|---|---|---|
| IRX vs OR-Tools | Solomon + Li-Lim fast | `1W / 5T / 0L`, `-0.096%` distance, `-1` vehicle |
| IRX vs VROOM | Li-Lim LC/LR/LRC101 | `0W / 1T / 2L`, `+2.28%` distance, `+2` vehicles |
| IRX vs PyVRP | Solomon C/R/RC101 | `2W / 0T / 1L`, `+0.011%` distance, `-3` vehicles |

Conclusion: IRX is competitive in static smoke tests, but VROOM remains stronger on selected Li-Lim static routing cases.

## 2. Industry Live Dispatch Benchmark

Artifact:

- `artifacts/benchmark/industry_grade_dispatch_benchmark_20260531/industry_grade_dispatch_benchmark.md`

Protocol: `5 scenarios x 5 seeds x 5 baselines`.

| Metric | VROOM Rolling | Full Adaptive | Delta |
|---|---:|---:|---:|
| Served orders | `8758` | `9254` | `+496` |
| On-time rate | `0.844` | `0.937` | `+9.3 pp` |
| Late count | `1420` | `587` | `-58.7%` |
| Avg wait | `8.667` | `4.055` | `-53.2%` |
| Bundle rate | `0.458` | `0.578` | `+12.0 pp` |
| Utilization | `0.801` | `0.897` | `+9.6 pp` |
| Distance/order | `1.224` | `1.096` | `-10.5%` |
| Violations | `0` | `0` | `0` |

Conclusion: Full Adaptive outperforms VROOM rolling on live dispatch KPIs under synthetic multi-seed workloads.

## 3. Ablation Study

Artifact:

- `artifacts/benchmark/adaptive_bundle_ablation_benchmark_20260531/adaptive_bundle_ablation_report.md`

| Config | Served | Late | Avg wait | Bundle | Utilization | Distance | Runtime p95 | Violations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A0 Baseline | `8478` | `1537` | `8.864` | `0.408` | `0.768` | `11392.098` | `632` | `0` |
| A6 Full Adaptive | `9254` | `587` | `4.055` | `0.578` | `0.897` | `9874.778` | `875` | `0` |

A0 -> A6:

- Served: `+776`
- Late: `-61.8%`
- Avg wait: `-54.3%`
- Bundle rate: `+17.0 pp`
- Utilization: `+12.9 pp`
- Distance: `-13.3%`
- Violations: `0`

Largest module gains:

- Convenient Insertion: late `-26.0%`, wait `-33.5%`
- Destroy-Repair: late `-23.6%`

Conclusion: each adaptive module contributes; insertion and repair are the largest KPI levers.

## 4. Adversarial Stress Benchmark

Artifacts:

- `artifacts/benchmark/adversarial_live_dispatch_20260531/adversarial_live_dispatch_benchmark.md`
- `artifacts/benchmark/adversarial_live_dispatch_after_budget_20260531/adversarial_live_dispatch_benchmark.md`

Stress setup:

- 90-minute simulation
- demand burst `4x`
- `15%` sparse outliers
- `30%` tight deadlines
- `20%` delayed drivers with `40%` speed drop
- `50%` capacity pressure

Before optimization, bottlenecks:

- `runtime-p99-too-high`
- `order-admission-aging-too-weak`
- `convenient-insertion-needs-deadline-safety`

After optimization:

| Metric | Before | After | Target | Result |
|---|---:|---:|---:|---|
| Runtime p99 | `2576 ms` | `1443 ms` | `<1500 ms` | PASS |
| Max order age | `85.752` | `53.166` | `<60` | PASS |
| Late count | `856` | `667` | no regression | PASS |
| P95 wait | `44.316` | `44.316` | hold/reduce | PASS |
| Bundle rate | `0.431` | `0.431` | no major drop | PASS |
| Violations | `0` | `0` | `0` | PASS |

Diagnosis after optimization: `no-critical-breakage-detected` on `5/5 seeds`.

## Demo Flow

Recommended 3-minute demo:

1. Nearby same-direction orders create a bundle.
2. A driver already moving receives a deadline-safe convenient insertion behind the frozen stop.
3. A risky bundle triggers breakRisk and bounded destroy-repair before commit.

## Limitations

- Benchmarks are synthetic deterministic simulations, not public real-world dispatch replay.
- ML is currently learning-assisted scoring/policy integration; it is not a fully trained deep RL controller.
- VROOM remains stronger on selected static Li-Lim routing cases.
- Runtime p99 is now within target but still higher than VROOM rolling.

## Final Claim

IRX combines a competitive solver portfolio with an Adaptive Bundle Dispatch Layer. The solver portfolio supports static route quality, while the Adaptive Layer improves live rolling dispatch decisions: admission, bundling, matching, insertion, repair, and no-regress safety.
