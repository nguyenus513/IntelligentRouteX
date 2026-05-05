# Overnight Community Benchmark International Report

Run source: `artifacts/benchmark/overnight_no_vroom_20260505_010106`  
Run window: `2026-05-05 01:01:06 +07:00` to `2026-05-05 13:13:00 +07:00`  
Scope: community/external benchmark evaluation only. This report intentionally excludes VROOM comparison and does not treat Phase 100/Phase 99 guard results as the main community benchmark evidence.

## Executive Conclusion

IntelligentRouteX is now benchmarkable against community-style datasets and external benchmark suites without relying on hardcoded targets or comparator leakage. The strongest evidence is in ML readiness/value, dynamic dispatch stability, route-beauty, traffic-aware routing, weather-aware routing, and clean Solomon/Li-Lim feasibility. The main remaining international-quality gap is academic routing competitiveness on large Li-Lim-heavy benchmarks: the system is feasible and safe, but not yet state-of-the-art on distance quality or vehicle-count minimization compared with the OR-Tools baseline used in the large community run.

International-standard interpretation:

- **ML intelligence:** PASS. Evidence-grade readiness and ablation value are present across forecast, GreedRL, RouteFinder, and tabular components.
- **Routing feasibility/safety:** PASS to PASS_WITH_LIMITS. Solomon core passes cleanly; Li-Lim core is feasible but has vehicle-count gaps on LR101/LRC101.
- **Academic routing competitiveness:** PASS_WITH_LIMITS. Large benchmark fully completed, but distance quality loses to OR-Tools in most paired feasible comparisons.
- **Operational dispatch and environment-aware routing:** mostly PASS. Dynamic dispatch, route beauty, traffic, and weather benchmarks are clean. Food dispatch is PASS_WITH_LIMITS due to end-to-end tail-quality gaps.
- **Production claim:** not promoted by this report. The evidence supports a benchmarkable, shadow-mode/diagnostic-quality optimizer, not a claim of global routing SOTA or full production-main readiness.

## Methodology

The benchmark campaign used the no-VROOM overnight artifact root and included community/external suites for routing, dispatch, ML, traffic, weather, and route aesthetics. The run completed all planned steps, but some steps returned nonzero process exits due to guard/config verdicts rather than a total benchmark crash.

High-level run status:

| Category | Result |
|---|---:|
| Overall overnight state | completed |
| Total steps | 16 |
| Process PASS steps | 12 |
| Process FAIL/nonzero steps | 4 |
| Large community cells completed | 720 / 720 |
| VROOM comparison | excluded by scope |

Nonzero process steps are interpreted carefully:

- `phase15-large-community` exited `1` after producing complete `720/720` results; this is a quality/verdict failure, not an execution crash.
- `phase90-final-quality-all-suites`, `phase90-victory-guard`, and `academic-max-quality` are system/guard/config-oriented and are not the primary community benchmark evidence in this report.

## Routing Benchmarks

### External Solomon Core

Source: `03_external_solomon_core/external_benchmark_results.json`

| Instance | Verdict | Distance | Vehicles | Runtime |
|---|---:|---:|---:|---:|
| C101 | PASS | 828.9369 | 10 | 60.672s |
| R101 | PASS | 1653.5332 | 19 | 60.597s |
| RC101 | PASS | 1696.9492 | 14 | 60.522s |

Assessment:

- Solomon core is clean: all three benchmark-native instances pass.
- This supports basic international routing feasibility evidence across clustered, random, and mixed Solomon structures.
- The run is not enough to claim state-of-the-art Solomon performance, but it is enough to show the solver can execute and produce feasible benchmark-native solutions on canonical VRPTW-style community cases.

### External Li-Lim Core

Source: `04_external_li_lim_core/external_benchmark_results.json`

| Instance | Verdict | Feasible | Distance | Best Known Distance | Gap | Vehicles | Best Known Vehicles | Main Limitation |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| LC101 | PASS | true | 828.9369 | n/a | n/a | 10 | n/a | none in artifact |
| LR101 | PASS_WITH_LIMITS | true | 1693.5197 | 1650.8 | 2.5878% | 20 | 19 | vehicle-count-above-best-known |
| LRC101 | PASS_WITH_LIMITS | true | 1732.4347 | 1708.8 | 1.3831% | 16 | 14 | vehicle-count-above-best-known |

Assessment:

- Li-Lim core is feasible and stable: no accepted hard-violation result is reported here.
- The weakness is quality, especially vehicle count on LR101 and LRC101.
- In international PDPTW terms, this is a credible feasibility baseline but not a competitive academic optimum-level result.

### Phase15 Large Community Routing

Source: `07_phase15_large_community/phase15_large_benchmark_results.json`

| Metric | Value |
|---|---:|
| Completed cells | 720 / 720 |
| Runtime | 41,169,325 ms, about 11.4 hours |
| Solvers | `our-dispatch-v2`, `ortools-baseline` |
| Solomon cells | 12 |
| Li-Lim cells | 708 |
| PASS | 6 |
| PASS_WITH_LIMITS | 685 |
| FAIL | 9 |
| EVIDENCE_GAP | 20 |
| Feasible rows | 699 |
| Hard-violation rows | 1 |
| Paired feasible comparisons | 345 |

Paired feasible comparison versus OR-Tools baseline:

| Objective Dimension | Wins | Ties | Losses | Interpretation |
|---|---:|---:|---:|---|
| Distance | 25 | 73 | 247 | Not competitive on distance over this large Li-Lim-heavy set |
| Vehicles | 17 | 289 | 39 | Mostly tied on vehicle count, but still has material losses |

Best-known-solution gap statistics where available:

| Statistic | Gap |
|---|---:|
| Count | 12 |
| Average | 0.3984% |
| Median | 0.0831% |
| Minimum | -1.0809% |
| Maximum | 2.5878% |

Assessment:

- The large community run is important because it completed all `720/720` benchmark cells over an overnight-scale run.
- The solver demonstrates broad feasibility and benchmark integration, but quality is not yet internationally competitive against the OR-Tools baseline on distance.
- The correct academic conclusion is not “solver is weak” in general; it is narrower: the solver is safe and benchmarkable, but large Li-Lim routing quality remains below a strong baseline, especially in distance minimization.
- The single hard-violation row means the large benchmark layer still needs regression guard attention before any strong production-quality claim, even though Phase 99/100 diagnostic guards are clean.

### Phase15 Gap Community Routing

Source: `08_phase15_gap_community/phase15_large_benchmark_results.json`

| Metric | Value |
|---|---:|
| Completed cells | 6 / 6 |
| PASS | 1 |
| PASS_WITH_LIMITS | 5 |
| Feasible rows | 6 |
| Hard-violation rows | 0 |
| Paired feasible comparisons | 3 |

Paired feasible comparison versus OR-Tools baseline:

| Objective Dimension | Wins | Ties | Losses |
|---|---:|---:|---:|
| Distance | 0 | 0 | 3 |
| Vehicles | 1 | 1 | 1 |

Assessment:

- This smaller gap-focused run is clean on feasibility and hard violations.
- It confirms the same quality pattern: vehicle count can be competitive in some cases, but distance quality lags the OR-Tools baseline on the paired feasible rows.

## Dispatch Benchmarks

### Food Dispatch Quality

Source: `11_food_dispatch_quality/food_dispatch_quality_results.json`

Benchmark family: `grubhub-mdrplib-quality-thresholds`  
Final verdict: `PASS_WITH_LIMITS`

Layer verdicts:

| Layer | Score | Verdict | Main Blocker |
|---|---:|---:|---|
| bundleQuality | 0.8693 | PASS_WITH_LIMITS | food-quality-target-gap |
| driverAssignmentQuality | 0.9436 | PASS | none |
| anchorQuality | 0.8322 | PASS_WITH_LIMITS | anchor-quality-target-gap |
| pickupSequenceQuality | 0.9045 | PASS | none |
| dropoffSequenceQuality | 0.9045 | PASS | none |
| orderToDeliveryQuality | 0.4968 | PASS_WITH_LIMITS | order-to-delivery-quality-target-gap |

Operational metrics:

| Metric | Value |
|---|---:|
| servedOrderRate | 1.0 |
| lateOrderRate | 0.0 |
| p95DelayMax | 12.2119 |
| p95FoodOnVehicleTimeMax | 11.4652 |
| avgOrderToDeliveryTime | 23.6063 |
| p95OrderToDeliveryTimeMax | 48.9516 |
| courierUtilization | 0.9848 |
| assignmentFairnessGini | 0.1418 |
| courierShiftViolation | 0 |
| pickupBeforeDropoffViolation | 0 |

Assessment:

- Food dispatch is operationally safe in the tested rows: served rate is complete, late order rate is zero, and no pickup/dropoff or shift violations are reported.
- International-quality limitation is tail service quality, especially order-to-delivery quality and bundle/anchor quality.
- This is suitable evidence for a strong prototype or shadow-mode benchmark, not yet a full production food-delivery optimization claim.

### Dynamic Dispatch Quality

Source: `12_dynamic_dispatch_quality/dynamic_dispatch_quality_results.json`

| Metric | Value |
|---|---:|
| Final verdict | PASS |
| Row count | 3 |
| Hard violations | 0 |
| Average route stability score | 1.0 |
| Baseline comparison available | true |
| Served-order delta vs baseline | 0 |
| Total tardiness delta vs baseline | 0.0 |

Assessment:

- Dynamic dispatch is a clean PASS in the current community-style stress benchmark.
- Stability is excellent in the evaluated rows.
- Because row count is small, this is strong smoke/benchmark evidence, not yet a broad-scale stochastic dispatch certification.

## Route Beauty, Traffic, and Weather Benchmarks

### Route Beauty Large

Source: `13_route_beauty_large/route_beauty_results.json`

Benchmark family: `dimacs-road`  
Data source: `DIMACS 9th Implementation Challenge USA-road-d`  
Final verdict: `PASS`

| Metric | Value |
|---|---:|
| Evaluated pairs | 169 |
| Requested pairs | 200 |
| Region count | 1 |
| Bad route count | 0 |
| High-detour route count | 0 |
| Low-straightness route count | 0 |
| Beauty-improved route count | 36 |
| Dominance-rejected route count | 163 |
| Average route quality score | 0.7848 |
| Average straightness score | 0.7226 |
| Average network detour ratio | 1.4355 |
| Average turn count | 10.4793 |

Assessment:

- Route-beauty selection is clean on the evaluated DIMACS-derived routes.
- The system avoids bad, high-detour, and low-straightness routes in this benchmark.
- Limitation: geographic diversity is narrow in this artifact because `regionCount = 1`.

### Traffic-Aware Routing

Source: `14_traffic_route_large/traffic_route_results.json`

Final verdict: `PASS`

| Dataset | Route Count | Bad Traffic Routes | Average Peak/Off-Peak Ratio |
|---|---:|---:|---:|
| METR-LA | 183 | 0 | 3.2101 |
| PEMS-BAY | 84 | 0 | 0.9598 |

Assessment:

- Traffic-aware routing passes on both community traffic datasets.
- No bad traffic routes are reported in the evaluated set.
- METR-LA shows high peak/off-peak contrast, so the benchmark has meaningful traffic stress rather than only trivial low-variance cases.

### Weather-Aware Routing

Source: `15_weather_route_large/weather_route_results.json`

Final verdict: `PASS`

| Dataset | Route Count | Bad Weather Routes | Rain Events | Wind Events | Weather Events | Avg Weather Cost Ratio |
|---|---:|---:|---:|---:|---:|---:|
| open-meteo-ny | 507 | 0 | 3 | 1 | 3 | 1.5808 |

Assessment:

- Weather-aware routing passes cleanly in the New York Open-Meteo scenario.
- No bad weather route is reported despite nonzero rain/wind stress.
- This is useful operational-routing evidence, but broader climate/region coverage would be needed for an international production claim.

## ML Intelligence Benchmark

Source: `16_ml_intelligence/ml_intelligence_results.json`

Benchmark family: `rl4co`  
Final verdict: `PASS`

### Readiness Evidence

| Metric | Value |
|---|---:|
| ML value proven | true |
| Worker readiness audited | true |
| RL4CO available/importable | true / true |
| RL4CO version | 0.6.0 |
| Torch available/importable | true / true |
| Torch version | 2.10.0+cu128 |
| CUDA available | true |
| CUDA device count | 1 |
| Local ML policy adapter present | true |
| ML ablation artifact count | 27 |
| ML ablation rows | 20 |
| Positive ablation count | 6 |
| Positive components | forecast, greedrl, routefinder, tabular |

Worker readiness:

| Worker | Implementation Present | Ready |
|---|---:|---:|
| forecast | true | true |
| greedrl | true | true |
| routefinder | true | true |
| tabular | true | true |

International ML assessment:

- This is the strongest part of the community benchmark package.
- The artifact contains three important evidence layers: dependency/runtime readiness, worker readiness, and ablation evidence.
- Positive ablations across four ML components support the claim that ML contributes measurable value, rather than merely existing as unused code.
- CUDA availability is proven at environment level, but this report should not overclaim that every worker path actively used GPU acceleration during the readiness probe.
- The ML evidence is suitable for an applied-research or engineering benchmark report. For a top-tier ML paper claim, the next step would be repeated statistical trials with confidence intervals, fixed random seeds, train/test splits, and stronger non-ML baselines.

## International-Standard Rating

| Area | Verdict | International Interpretation |
|---|---:|---|
| ML intelligence | PASS | Evidence-grade applied ML readiness and positive ablation value are present. |
| Solomon routing core | PASS | Feasible benchmark-native routing on canonical community instances. |
| Li-Lim routing core | PASS_WITH_LIMITS | Feasible, but vehicle-count gaps remain on LR101/LRC101. |
| Large academic/community routing | PASS_WITH_LIMITS | Fully benchmarked, broadly feasible, but not competitive with OR-Tools on distance. |
| Food dispatch | PASS_WITH_LIMITS | Safe and operationally strong, but end-to-end tail quality and bundle/anchor quality need improvement. |
| Dynamic dispatch | PASS | Stable, no hard violations in evaluated rows. |
| Route beauty | PASS | Clean route-shape benchmark, limited by one-region coverage. |
| Traffic-aware routing | PASS | Clean on METR-LA and PEMS-BAY route stress. |
| Weather-aware routing | PASS | Clean on Open-Meteo NY weather stress. |

## Key Strengths

1. The system is no longer only a local demo: it produced complete overnight community benchmark artifacts.
2. ML is evidence-backed: runtime readiness, worker readiness, and ablation value are all present.
3. Dynamic dispatch, traffic routing, weather routing, and route beauty are clean PASS in their current community artifacts.
4. Solomon and Li-Lim core runs show feasible routing behavior on canonical benchmark families.
5. Large community routing completed `720/720` cells, which is a meaningful benchmark execution milestone.

## Key Limitations

1. Large academic routing quality is not yet state-of-the-art: distance loses to OR-Tools in `247/345` paired feasible comparisons.
2. Vehicle count is mostly tied against OR-Tools, but still has `39/345` losses and Li-Lim core vehicle-count gaps on LR101/LRC101.
3. Phase15 large community contains `1` hard-violation row; this must be investigated before using the large suite as production-safety certification.
4. Food dispatch is not a full PASS because order-to-delivery, bundle, and anchor quality remain below target.
5. Traffic/weather/beauty evidence is promising but still dataset-limited; broader geographic and temporal coverage would strengthen the claim.

## Final Judgment

IntelligentRouteX meets a credible international engineering-benchmark standard for ML readiness/value, safety-oriented routing feasibility, dynamic dispatch stability, and environment-aware route selection. It does not yet meet an international state-of-the-art academic routing standard on large Li-Lim-heavy optimization quality, because distance competitiveness against OR-Tools is weak and some vehicle-count gaps remain.

The most accurate final statement is:

> IntelligentRouteX is a benchmarkable, non-hardcoded, ML-enabled routing and dispatch system with strong community evidence in ML, dynamic dispatch, route beauty, traffic, and weather routing. Academic routing quality is feasible and safe in core benchmarks but remains PASS_WITH_LIMITS on large community Li-Lim-heavy evaluation because optimization quality, especially distance and vehicle count, is not yet competitive with a strong OR-Tools baseline.

## Recommended Next Benchmark Work

1. Investigate the single hard-violation row in Phase15 large community and add a regression guard for it.
2. Split academic routing evaluation into Solomon-only, Li-Lim-only, and mixed PDPTW reports with separate quality targets.
3. Add repeated ML ablation trials with seeds, confidence intervals, and per-component effect sizes.
4. Expand weather and traffic benchmarks across more regions and time windows.
5. Improve Li-Lim distance quality via generic decomposition/search-strength work, not benchmark-name rules or target-K forcing.
