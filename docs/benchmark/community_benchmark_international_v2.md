# Community Benchmark Report v2

System: IntelligentRouteX  
Benchmark source commit: `2a394e3c`  
Initial report commit: `795efc96`  
Reproducibility artifact commit: `fcb3441a`  
Report date: `2026-05-05`  
Primary artifact roots:

- `artifacts/benchmark/overnight_no_vroom_20260505_010106`
- `artifacts/benchmark/vroom_live_smoke_20260505`
- `artifacts/benchmark/vroom_lilim8_live_20260505`
- `artifacts/benchmark/community_benchmark_tables_v2`

This report rewrites the previous engineering summary into a benchmark-paper style report. The main sections use numeric metrics only: vehicle count, distance, gap, runtime, feasible rate, violation counts, latency, ablation deltas, and missing-data labels. Internal verdict labels are not used as evidence in the main results.

## Abstract

We evaluate IntelligentRouteX on community-standard routing and dispatch workloads, including Solomon-style VRPTW, Li-Lim PDPTW, VROOM capability cases, Li-Lim VROOM live comparison, dynamic dispatch, food dispatch quality, traffic-aware routing, weather-aware routing, route beauty, and ML-assisted routing evidence.

The strongest current evidence is feasibility-oriented routing, ML readiness, ML ablation value, dynamic dispatch stability, and environment-aware route selection. The main research gap remains large-scale academic PDPTW quality: under the current benchmark protocol, IntelligentRouteX trails OR-Tools on distance in many paired feasible Li-Lim comparisons, and trails VROOM on the feasible Li-Lim live rows collected in this campaign.

## 1. Overview

### 1.1 Objective

The objective is to measure whether IntelligentRouteX is competitive under reproducible benchmark conditions, not merely whether it satisfies internal gates.

Problem families:

| Family | Benchmark source | Main objective |
|---|---|---|
| Static VRPTW | Solomon-style community rows | Minimize vehicle count, then distance |
| Static PDPTW | Li-Lim community rows | Minimize vehicle count, then distance |
| Industrial comparator | VROOM live service | Compare feasibility, vehicle count, distance, timeout |
| Dynamic dispatch | Community-style dynamic dispatch rows | Minimize violations, tardiness, instability |
| Food dispatch | Grubhub/MDRP-style threshold rows | Minimize delivery tail, lateness, unfairness |
| ML-assisted routing | RL4CO/worker readiness and ablation artifacts | Improve objective and robustness over non-ML selection |

### 1.2 Claims Supported by This Artifact

- On the generated VROOM capability smoke suite, VROOM returned feasible solutions on `4/4` rows; IntelligentRouteX matched VROOM on `3/4` rows and had lower distance on `1/4` row.
- On the live Li-Lim VROOM comparator, VROOM returned feasible checked solutions on `4/8` rows and timed out on `2/8`; among comparable feasible rows, IntelligentRouteX had an average distance gap of `8.131%` and an average vehicle gap of `+0.75` versus VROOM.
- On the large Phase15 community run, IntelligentRouteX completed paired comparison against OR-Tools over `360` instances; feasible rate was `100.0%` for medium and large Li-Lim groups and `80.822%` for small Li-Lim.
- On Li-Lim medium and large groups, the average distance gap versus OR-Tools was `1.409%` and `2.076%`, respectively.
- ML components are present and importable; the artifact contains `20` ablation rows, with positive rows for forecast, GreedRL, and RouteFinder components.

## 2. Experimental Setup

### 2.1 Hardware and Runtime

| Component | Value |
|---|---|
| OS | Windows host, PowerShell execution environment |
| Python | `3.13` for benchmark runners |
| Docker | Docker Desktop service, VROOM container exposed on `localhost:3000` |
| GPU availability | CUDA visible in ML artifact |
| CUDA device count | `1` |
| Torch version | `2.10.0+cu128` |
| RL4CO version | `0.6.0` |

Hardware detail is sufficient for an engineering benchmark record but not yet complete for a paper-grade reproducibility appendix. CPU model, RAM, exact GPU model, and pinned Docker image digest should be added in the next reproducibility audit.

### 2.2 Software Baselines

| Baseline | Status in this campaign | Evidence source |
|---|---|---|
| OR-Tools | measured | Phase15 large community paired rows |
| VROOM | measured live | `vroom_live_smoke_20260505`, `vroom_lilim8_live_20260505` |
| PyVRP | not measured | PyVRP bridge exists, but no current v2 table artifact |
| RL4CO | runtime available | ML intelligence artifact, version `0.6.0` |
| RouteFinder-style worker | worker ready and ablation rows present | ML intelligence artifact |

PyVRP is intentionally not assigned synthetic numbers. The current report marks it as `not measured` because this benchmark campaign did not produce a PyVRP-vs-ours numeric table under the same protocol.

### 2.3 Time Limits

| Benchmark | Time limit |
|---|---:|
| Phase15 large community rows | `60s` per cell |
| VROOM capability smoke challenger | `10s` |
| VROOM capability smoke VROOM timeout | `30s` |
| VROOM Li-Lim challenger | `15s` |
| VROOM Li-Lim VROOM timeout | `60s` |
| Food dispatch quality | artifact-defined |
| Dynamic dispatch quality | artifact-defined |
| ML ablation/readiness | artifact-defined |

### 2.4 Random Seeds

The current benchmark artifacts do not provide a complete seed-level repeated-trial table. Therefore, statistical reporting is limited to cross-instance mean and standard deviation where multiple rows exist. Paper-grade reporting should rerun key benchmarks with fixed seeds such as `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]` and report mean +/- std over seeds.

## 3. Metrics

### 3.1 Static Routing Metrics

| Metric | Definition |
|---|---|
| Vehicle count | Number of active vehicles in a feasible solution |
| Total distance | Sum of route distances in benchmark-native units |
| Vehicle gap | Ours vehicles minus baseline vehicles |
| Distance gap (%) | `(ours_distance - baseline_distance) / baseline_distance x 100` |
| Gap to BKS (%) | `(ours_distance - BKS_distance) / BKS_distance x 100` |
| Runtime | Wall-clock benchmark runtime |
| Feasible rate | Fraction of rows with all hard constraints satisfied |
| Timeout rate | Fraction of rows where solver exceeded configured time limit |

### 3.2 Dynamic and Food Dispatch Metrics

| Metric | Definition |
|---|---|
| Average delivery time | Mean order completion time |
| P95 delivery / delay | 95th percentile tail metric from artifact |
| SLA violation / late order rate | Fraction of orders violating service promise |
| Courier utilization | Active courier utilization ratio |
| Fairness Gini | Assignment fairness inequality measure |
| Cost per order | `not measured` in current artifact |
| P99 latency | `not measured` in current artifact |

### 3.3 ML Metrics

| Metric | Definition |
|---|---|
| Selector objective delta | Objective change attributed to an ML component in ablation rows |
| Robust utility delta | Robustness utility change in ablation rows |
| Positive ablation rows | Rows with positive selector or robust utility contribution |
| Inference time | `not measured` in current artifact |
| Training cost | `not measured` in current artifact |

## 4. Missing Data Policy

No raw missing-value placeholders are used in the main report.

| Label | Meaning |
|---|---|
| `-` | Not applicable by design |
| `not measured` | Pipeline did not collect this metric in the current artifact |
| `timeout` | Solver exceeded the configured time limit |
| `infeasible` | Checker did not validate all hard constraints |
| `failed` | Metric computation or solver execution failed |

## 5. Static Routing Results

### 5.1 Aggregate Routing Against OR-Tools

Source: `artifacts/benchmark/community_benchmark_tables_v2/routing_phase15_summary.csv`

| Dataset | Scale | Instances | Paired feasible | Feasible rate (%) | Vehicle gap vs OR-Tools | Distance gap vs OR-Tools (%) | Runtime (s) | Hard-violation rows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Li-Lim | large | 104 | 104 | 100.000 | 0.087 | 2.076 | 56.171 | 0 |
| Li-Lim | medium | 177 | 176 | 100.000 | 0.057 | 1.409 | 53.388 | 0 |
| Li-Lim | small | 73 | 59 | 80.822 | 0.119 | 1.661 | 45.022 | 0 |
| Solomon-style | small | 6 | 6 | 100.000 | -1.833 | 3.580 | 60.580 | 0 |

Interpretation:

- The Li-Lim medium and large rows show complete feasibility in the Phase15 paired artifact and low but positive average distance gap versus OR-Tools.
- The Li-Lim small group has a lower feasible rate (`80.822%`), which should be investigated before making a broad small-instance quality claim.
- The Solomon-style small group uses fewer vehicles on average than OR-Tools in this artifact (`-1.833` vehicle gap), but with a higher distance gap (`3.580%`). This indicates a hierarchical trade-off: vehicle minimization may be stronger than distance polish in those rows.

### 5.2 VROOM Capability Smoke Live Comparator

Source: `artifacts/benchmark/vroom_live_smoke_20260505`

| Metric | Value |
|---|---:|
| Rows | 4 |
| VROOM status `ok` | 4 |
| VROOM feasible by internal checker | 4 |
| VROOM timeout rows | 0 |
| Comparable rows | 4 |
| Equal-distance rows | 3 |
| Ours lower-distance rows | 1 |

Per-instance summary:

| Instance | VROOM status | VROOM feasible | VROOM distance | Ours distance | Distance relation |
|---|---|---:|---:|---:|---|
| single_shipment | ok | yes | 10.606 | 10.606 | equal |
| two_shipments_same_driver_bundle | ok | yes | 13.708 | 12.606 | ours lower |
| waiting_required | ok | yes | 4.000 | 4.000 | equal |
| custom_matrix_asymmetric | ok | yes | 17.406 | 17.406 | equal |

Interpretation:

- VROOM is now operational and data-producing through Docker on `localhost:3000`.
- Capability smoke confirms adapter compatibility for small pickup-delivery and custom-matrix cases.
- This is not a large academic quality benchmark; it is a live integration and semantic capability check.

### 5.3 VROOM Li-Lim Live Comparator

Source: `artifacts/benchmark/community_benchmark_tables_v2/vroom_lilim_live.csv`

| Instance | VROOM status | VROOM feasible | VROOM vehicles / distance | Ours vehicles / distance | Vehicle gap | Distance gap (%) | VROOM runtime (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| LRC202 | ok | no | 4 / 1398.020 | 5 / 1591.021 | - | - | 534 |
| LRC206 | ok | yes | 3 / 1159.033 | 4 / 1348.841 | 1 | 16.376 | 386 |
| LRC106 | ok | yes | 12 / 1474.085 | 12 / 1489.758 | 0 | 1.063 | 408 |
| LRC104 | ok | yes | 10 / 1129.338 | 11 / 1170.620 | 1 | 3.655 | 417 |
| LRC108 | ok | yes | 11 / 1167.174 | 12 / 1300.589 | 1 | 11.431 | 345 |
| LRC1_2_7 | ok | no | 17 / 3419.307 | 17 / 3782.925 | - | - | 1781 |
| LRC281 | timeout | no | - | 94 / 73280.848 | - | - | 60120 |
| LC1_4_8 | timeout | no | - | 43 / 10026.852 | - | - | 60076 |

Aggregate VROOM Li-Lim live comparator:

| Metric | Value |
|---|---:|
| Rows | 8 |
| VROOM status `ok` | 6 |
| VROOM feasible rows | 4 |
| VROOM timeout rows | 2 |
| Comparable feasible rows | 4 |
| Mean vehicle gap vs VROOM | +0.750 |
| Mean distance gap vs VROOM | +8.131% |
| Std distance gap vs VROOM | 7.095% |

Interpretation:

- VROOM is a strong live baseline on the feasible Li-Lim rows; IntelligentRouteX trails it on mean distance and vehicle count in this sample.
- Two VROOM rows were returned but failed the internal checker, and two rows timed out under the configured `60s` VROOM timeout. These rows are not included in distance-gap averages.
- The fair conclusion is: IntelligentRouteX is comparable and feasible on several Li-Lim rows, but it is not stronger than VROOM on this live Li-Lim sample.

## 6. Dispatch Results

### 6.1 Food Dispatch Numeric Metrics

Source: `artifacts/benchmark/overnight_no_vroom_20260505_010106/11_food_dispatch_quality/food_dispatch_quality_results.json`

| Metric | Value |
|---|---:|
| Row count | 3 |
| Served order rate | 100.000% |
| Late order rate | 0.000% |
| P95 delay | 12.212 |
| P95 food-on-vehicle time | 11.465 |
| Average order-to-delivery time | 23.606 |
| P95 order-to-delivery time | 48.952 |
| Courier utilization | 98.485% |
| Assignment fairness Gini | 0.142 |
| Courier shift violations | 0 |
| Pickup-before-dropoff violations | 0 |
| Cost per order | not measured |
| P99 latency | not measured |

Interpretation:

- The tested food-dispatch rows show complete service coverage, no late orders, and no hard assignment-sequence violations.
- Tail delivery quality is the main measurable pressure point: P95 order-to-delivery time is `48.952` in artifact units.
- Cost per order and P99 latency are not measured; they must be added before a production dispatch paper claim.

### 6.2 Dynamic Dispatch Numeric Metrics

Source: `artifacts/benchmark/overnight_no_vroom_20260505_010106/12_dynamic_dispatch_quality/dynamic_dispatch_quality_results.json`

| Metric | Value |
|---|---:|
| Row count | 3 |
| Hard violations | 0 |
| Average route stability score | 1.000 |
| Served order delta vs baseline | 0 |
| Total tardiness delta vs baseline | 0.000 |
| P95 latency | not measured |
| P99 latency | not measured |
| Cost per order | not measured |

Interpretation:

- Dynamic dispatch is stable in the current artifact: route stability is `1.000`, served-order delta is `0`, and tardiness delta is `0.000`.
- The current dynamic dispatch evidence is too small for a statistical claim because only `3` rows are present and tail latency is not measured.

## 7. ML Impact

Source: `artifacts/benchmark/overnight_no_vroom_20260505_010106/16_ml_intelligence/ml_intelligence_results.json`

### 7.1 ML Readiness

| Metric | Value |
|---|---|
| RL4CO importable | yes |
| RL4CO version | `0.6.0` |
| Torch importable | yes |
| Torch version | `2.10.0+cu128` |
| CUDA available | yes |
| CUDA device count | `1` |
| Local ML policy adapter | present |
| Ablation rows | `20` |
| Positive ablation rows | `6` |

### 7.2 ML Ablation Summary

Source: `artifacts/benchmark/community_benchmark_tables_v2/ml_ablation_summary.csv`

| Component | Rows | Positive rows | Mean selector delta | Std selector delta | Mean robust delta | Std robust delta | Inference time |
|---|---:|---:|---:|---:|---:|---:|---|
| forecast | 2 | 1 | -0.006 | 0.008 | 0.001 | 0.002 | not measured |
| greedrl | 15 | 1 | 0.012 | 0.047 | -0.026 | 0.045 | not measured |
| routefinder | 2 | 1 | 0.010 | 0.014 | 0.002 | 0.003 | not measured |
| tabular | 1 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | not measured |

Interpretation:

- The ML layer is installed, importable, and connected to worker readiness artifacts.
- Ablation evidence is mixed rather than uniformly positive: GreedRL has positive mean selector delta but negative mean robust utility delta; RouteFinder has positive selector and robust deltas in the small measured subset; forecast has slightly negative selector delta but positive robust delta.
- The current ML evidence supports "ML components are operational and sometimes beneficial", not "ML consistently improves every metric."
- Inference latency and training cost are not measured in the current artifact, so a paper-grade ML efficiency claim is still pending.

## 8. Statistical Validity

Current statistical strength:

| Area | Available statistics | Limitation |
|---|---|---|
| Phase15 routing | cross-instance mean, std, median available from generated CSV | seed-level repeated trials missing |
| VROOM smoke | per-instance comparison over 4 rows | too small for statistical significance |
| VROOM Li-Lim | per-instance comparison over 8 rows | VROOM infeasible/timeout rows reduce comparable sample to 4 |
| Food dispatch | row-level metrics over 3 rows | no P99, no cost/order, no multi-seed variance |
| Dynamic dispatch | row-level metrics over 3 rows | no tail latency, no multi-seed variance |
| ML ablation | component-level mean/std over 20 rows | inference cost and seed-level generalization not measured |

Recommended significance protocol:

| Comparison | Metric | Recommended test |
|---|---|---|
| Ours vs OR-Tools | paired distance gap | Wilcoxon signed-rank over feasible paired rows |
| Ours vs VROOM | paired distance gap | Wilcoxon signed-rank over VROOM-feasible rows |
| Ours + ML vs non-ML | objective delta | paired bootstrap confidence interval |
| Dispatch peak vs baseline | SLA/tardiness | bootstrap confidence interval over orders |

## 9. Failure Analysis

Phase-linked diagnostic history explains the remaining large-instance routing gap:

| Phase range | Bottleneck found | Fix direction | Current interpretation |
|---|---|---|---|
| 91-93 | candidate generation and decomposition scaling | operator activation, micro-probe, decomposition probe | generation works on micro/subproblem cases; full-scale quality remains harder |
| 94-95 | route-slot overflow during recombination | slot-preserving and slot-aware subproblem solving | slot overflow is prechecked instead of accepted as hard violation |
| 96 | coverage invalid after recombination | affected-route request closure and coverage repair | coverage preservation is cleaner |
| 97-98 | residual time-window infeasibility | TW repair and schedule-feasible subproblem construction | time-window violations were reduced upstream |
| 99 | final residual TW blocker | exact TW route finalizer and autonomous repair loop | diagnostic path reached clean final decomposition evidence |

The key research conclusion is that large Li-Lim performance is now primarily a search-efficiency and scaling problem, not a basic feasibility, adapter, hardcode, or telemetry problem.

## 10. Discussion

### 10.1 Strengths

- VROOM is now running live and produces comparator artifacts.
- IntelligentRouteX has complete numeric Phase15 tables against OR-Tools over `360` paired instances.
- Li-Lim medium and large feasibility in the generated Phase15 table is `100.000%` with zero hard-violation rows in those groups.
- Dynamic dispatch and food dispatch show zero hard violations in the evaluated artifacts.
- ML runtime readiness is real: RL4CO, Torch, CUDA visibility, and worker readiness are present.

### 10.2 Limitations

- PyVRP was not measured in this campaign, so the classical baseline set is incomplete.
- Seed-level repeated trials are missing, so the report is not yet statistically complete by NeurIPS/ICAPS-style standards.
- VROOM Li-Lim comparison has only `4` comparable feasible rows because VROOM had `2` checker-infeasible returns and `2` timeouts.
- Food and dynamic dispatch do not yet include P99 latency or cost per order.
- ML inference time and training cost are not measured.

### 10.3 Positioning

IntelligentRouteX should be considered research-grade in correctness, feasibility instrumentation, and benchmark integration. It should not yet be described as state-of-the-art on large PDPTW. Its main current advantage is broad system integration across routing, dispatch, ML, traffic, weather, and decomposition diagnostics. Its main research target is stronger large-instance search quality under fixed time budgets.

## 11. Reproducibility Checklist

| Item | Status |
|---|---|
| Dataset artifact paths recorded | yes |
| Git commit recorded | yes |
| VROOM service command documented | yes |
| VROOM live artifacts recorded | yes |
| OR-Tools artifact recorded | yes |
| PyVRP numeric artifact recorded | not measured |
| Time limits recorded | yes |
| Seeds recorded | not measured |
| Hardware fully recorded | partial |
| Raw CSV tables generated | yes |
| Table generator committed | yes |
| No raw missing-value placeholder in main report | yes |
| Internal verdict labels excluded from main results | yes |

## 12. Generated Table Artifacts

The following files are produced by `scripts/generate_benchmark_tables.py`:

| File | Purpose |
|---|---|
| `artifacts/benchmark/community_benchmark_tables_v2/community_benchmark_tables_v2.json` | Full normalized table bundle |
| `artifacts/benchmark/community_benchmark_tables_v2/routing_phase15_pairs.csv` | Per-instance OR-Tools vs ours table |
| `artifacts/benchmark/community_benchmark_tables_v2/routing_phase15_summary.csv` | Aggregate routing table by dataset/scale |
| `artifacts/benchmark/community_benchmark_tables_v2/vroom_lilim_live.csv` | VROOM Li-Lim live comparator rows |
| `artifacts/benchmark/community_benchmark_tables_v2/ml_ablation_summary.csv` | ML component ablation summary |
| `artifacts/benchmark/community_benchmark_tables_v2/generated_tables.md` | Markdown tables generated from artifacts |

Command:

```powershell
py -3.13 scripts/generate_benchmark_tables.py `
  --commit 2a394e3c `
  --source-commit 2a394e3c `
  --report-commit 795efc96 `
  --artifact-committed-in fcb3441a `
  --report-trace-commit 7d7d2725 `
  --output-dir artifacts/benchmark/community_benchmark_tables_v2
```

## 13. Final Conclusion

IntelligentRouteX now has a paper-style community benchmark report with numeric tables and live VROOM data. The system is feasible and robust across several evaluated routing and dispatch workloads, and the ML stack is operational with measurable ablation signals.

The strongest quantitative routing result is not superiority over all baselines; it is reproducible benchmarkability with clean numeric evidence. Against OR-Tools, Li-Lim medium and large average distance gaps are `1.409%` and `2.076%` in the generated Phase15 table. Against VROOM on the live Li-Lim sample, IntelligentRouteX trails by `8.131%` average distance over the four comparable feasible rows.

The next benchmark phase should add PyVRP under the same time limits, rerun seed-level trials, collect P99/cost metrics for dispatch, and measure ML inference overhead. Only after those additions should the report be treated as a full international paper-grade benchmark package.

