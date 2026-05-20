# IntelligentRouteX Benchmarks

This is the single benchmark source-of-truth for the repository. Older benchmark markdown files were consolidated here. When results overlap, this report keeps the best valid result, but preserves earlier negative evidence where it explains a later recovery.

Latest strongest run:

- Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/final-summary.json`
- Result: PASS
- Scope: compile, solver readiness, static standard, dynamic safety smoke, ML no-regress, official Solomon/Li & Lim smoke

## Benchmark Principles

- Do not tune thresholds to claim pass.
- Do not hardcode benchmark instances or BKS values.
- Every claim must cite artifact paths and measured deltas.
- Runtime certification and quality claims are separate.
- LLM benchmark cells, provider preflight, and prompt-validation rails are disabled by policy.
- Dynamic latency/churn/SLA improvements remain hypotheses until measured against fair rerun baselines.

## Objective Comparator

Static comparator order:

1. coverage higher
2. hard violations lower
3. late count lower
4. total lateness lower
5. vehicle/route count lower
6. distance lower
7. runtime lower

CVRP emphasizes capacity feasibility, fleet size, distance, and runtime. VRPTW/PDPTW emphasizes hard feasibility, lateness/time warp, fleet size, distance, and runtime.

## Solver Rows

Static datasets should distinguish:

- `GREEDY_BASELINE`
- `VROOM`
- `ORTOOLS`
- `PYVRP`
- `STRONGEST_BASELINE_CANDIDATE`
- `IRX_NATIVE`
- `IRX_HYBRID_FINAL`
- `IRX_IMPROVED_EXTERNAL`

## Claim Rules

- Static PASS: `IRX_HYBRID_FINAL` has zero loss versus the strongest baseline candidate under the unified comparator.
- Static WIN: IRX improves the strongest available candidate in the multi-solver portfolio without hard violations.
- Dynamic PASS: rolling dispatch safety holds.
- Dynamic WIN: requires measured decision latency, route churn, and SLA/on-time gains versus fair rerun baselines.
- ML PASS: no regression versus no-ML baseline.
- ML WIN: requires measured quality/runtime/search gain.

Do not publish 3x-10x latency, 50% churn reduction, or SLA gain as results. They remain hypotheses.

## Benchmark Families

### Academic Routing

Measures routing solver strength against public or known-hard routing families:

- Solomon VRPTW
- Li & Lim PDPTW
- Homberger VRPTW
- MDRPLib
- ICAPS / DPDP
- stochastic and SVRP-style community cases

Metrics include fleet efficiency, distance/objective quality, hard violations, competitiveness against strong public references, and robustness across C/R/RC structures.

### Food Dispatch Quality

Measures production dispatch quality, not only VRP score:

- bundle quality
- driver assignment quality
- anchor quality
- pickup sequence quality
- dropoff sequence quality
- order-to-delivery quality

Known bottleneck: order-to-delivery quality, especially p95/tail behavior.

### Route Beauty / Traffic / Weather

Metrics include detour ratio, straightness, turn count, sharp turns, zigzag behavior, traffic exposure, weather exposure, and route-condition robustness.

### ML Intelligence

Measures whether ML adds value versus no-ML / heuristic-only baselines. Current valid result is no-regress only, not measured quality gain.

### Dynamic Dispatch

Measures online behavior under changing state: hard violations, route stability, safe reassignment, response to new orders, burst scenarios, sparse scenarios, and rescue behavior.

### Runtime

Measures production budget behavior: p50/p95/p99 latency, candidate count, timeout rate, cache hit rate, in-flight event pressure, memory/CPU behavior, and queue pressure.

## v1.0.0 Production API Core

Artifact: `artifacts/test-reports/v1.0.0-production-api-core/final/final-summary.json`

The gate verifies compile, OpenAPI/AsyncAPI contracts, runtime store abstractions, queue/worker abstractions, static/live/rescue/compare APIs, execution timeline, security/idempotency/rate-limit hooks, artifact store, event stream, observability, and Docker Compose presence.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-production-api-core-gate.ps1 -BaseUrl http://localhost:18116 -OutputDir artifacts/test-reports/v1.0.0-production-api-core/final
```

## v0.9.10 ML-guided PD-LNS Seed Improver

Artifact: `artifacts/test-reports/v0.9.10-ml-guided-pd-lns/final-20case/ml-hybrid-pd-lns-final-summary.json`

Commits:

- `81fac1354`: ML-guided pickup-delivery destroy/repair
- `7d1c8a3c9`: no-regress hybrid cross insertion and swap-star
- `2376f79c2`: final 20-case gate evidence

Evidence:

| Metric | Result |
|---|---:|
| Status | PASS |
| Completed | 20/20 |
| Overall pass | true |
| ML best seed improved cases | 19/20 |
| ML-guided better than heuristic cases | 6/20 |
| Hybrid worse than AUTO cases | 0 |
| Total distance gain over best seed | 620.4 km |
| Late regression | 0 |
| Coverage regression | 0 |
| Pickup/dropoff violations | 0 |
| Capacity violations | 0 |
| Dominance failures | 0 |

Safe claim: IRX v0.9.10 uses ML-guided Hybrid PD-LNS to improve the strongest available routing candidate at pickup/dropoff sequence level. On the 20-case final gate, it improves the strongest seed candidate in 19/20 cases, beats heuristic PD-LNS in 6/20 cases, never regresses AUTO, and preserves coverage, lateness, pickup/dropoff precedence, capacity, and dominance.

Boundary: do not claim Hybrid always beats heuristic PD-LNS or wins on aggregate 20-case gain. Final evidence records `totalHybridGainKm=404.5` and `totalHeuristicGainKm=429.7`.

## v0.9.10-C Tri-model Fusion

Artifacts:

- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/fusion-5case/tri-model-fusion-summary.json`
- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/ablation-5case/tri-model-causal-ablation-summary.json`
- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/tri-model-decision-report.json`

Evidence:

| Metric | Result |
|---|---:|
| Status | PASS |
| Forecast called cases | 0 |
| Tabular called cases | 5/5 |
| RouteFinder called cases | 5/5 |
| GreedRL called cases | 5/5 |
| Fusion worse than best single model cases | 0 |
| Fusion better than best single model cases | 1/5 |
| Total fusion gain | 98.3 km |
| Total best single model gain | 96.5 km |
| Model workers with contribution | 3 |
| Pickup/dropoff violations | 0 |
| Capacity violations | 0 |
| Late regression | 0 |
| Coverage regression | 0 |
| Dominance failures | 0 |

Module decisions:

| Module | Decision |
|---|---|
| Adaptive Policy | KEEP_CORE |
| Tabular | KEEP_MODEL_STATIC |
| RouteFinder | KEEP_OPTIONAL_PROVIDER |
| GreedRL | KEEP_CONTROLLER_SELECTED |
| Forecast | OFF_STATIC_LIVE_RESCUE_ONLY |

Boundary: static PD-LNS fuses Tabular, RouteFinder, and GreedRL. Forecast is intentionally disabled for static seed improvement because static quality/risk gain was not proven.

## v0.9.11 Dynamic ML Dispatch

Target: `v0.9.11-dynamic-ml-dispatch-final`

Evidence path: `artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/`

Backend scope:

- live order intake
- driver telemetry updates
- freeze policy for active stops
- Forecast live risk diagnostics
- GreedRL live action selection
- tri-model repair diagnostics using Tabular, RouteFinder, and adaptive policy evidence
- live API contract
- event stream
- dynamic 6-case benchmark
- stress gate
- security/idempotency gate
- artifact evidence

Dashboard playground is intentionally deferred from backend certification.

## v1.0.1 Backend Core Recertification

Artifact: `artifacts/test-reports/v1.0.1-backend-core-recertified/final-summary.json`

After dashboard/mobile/demo cleanup, backend-only core was recertified with compile, production API core gate, static/live/compare smoke, execution timeline/events, Adaptive ML diagnostics, security, idempotency, rate-limit, event stream, and observability checks.

## v1.0.1 All-in-one Benchmark Runtime

Artifact: `artifacts/test-reports/v1.0.1-all-in-one-benchmark/final/final-summary.json`

| Check | Result |
|---|---:|
| Overall | PASS |
| Runtime | ALL_IN_ONE |
| VROOM readiness | PASS |
| OR-Tools readiness | PASS |
| PyVRP readiness | PASS |
| Static dispatch | PASS |
| Compare benchmark | PASS |
| Live dynamic | PASS |
| Execution timeline | PASS |
| Quality benchmark | PASS |
| Late regression | 0 |
| Dominance failures | 0 |

Smoke compare:

| Solver | Distance km |
|---|---:|
| IRX | 70.50 |
| VROOM | 71.21 |
| OR-Tools | 71.91 |

Valid claim: all-in-one runtime is certified and the smoke compare has IRX lower distance than VROOM and OR-Tools on that input.

## v1.0.2 Benchmark Suite Certification

Artifact: `artifacts/test-reports/v1.0.2-benchmark-suite-certification/final-summary.json`

This earlier run exposed that a single-candidate view was not sufficient before portfolio no-regress recovery.

| Check | Result |
|---|---:|
| Overall | PASS |
| Completed | 10/10 |
| IRX vs VROOM | 0W / 0T / 10L |
| IRX vs OR-Tools | 2W / 0T / 8L |
| Late regression | 0 |
| External late regression cases | 10 |
| Dominance failures | 0 |

Interpretation: the raw native row was not the correct final product claim for this compare suite. This result is kept because it explains why the final system uses a portfolio-level no-regress selector.

## v1.0.3 Portfolio No-regress Recovery

Artifact: `artifacts/test-reports/v1.0.3-external-seed-no-regress-recovery/final-summary.json`

| Check | Result |
|---|---:|
| Overall | PASS |
| Completed | 10/10 |
| IRX vs VROOM | 4W / 6T / 0L |
| IRX vs OR-Tools | 10W / 0T / 0L |
| Late regression | 0 |
| External late regression cases | 0 |
| Dominance failures | 0 |
| VROOM available | true |
| OR-Tools available | true |
| PyVRP available | true |

Valid claim: IRX Hybrid no-regress selector prevents loss versus the benchmark baseline candidate set on this 10-case suite.

## v1.0.2.1 Strongest Standard Rerun

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/final-summary.json`

| Check | Result |
|---|---:|
| Overall | PASS |
| Compile Java | PASS |
| Solver readiness | PASS |
| Static gate | PASS |
| Dynamic gate | PASS |
| ML gate | PASS |
| Official Solomon/LiLim gate | PASS |
| Runtime pass | true |
| Quality pass | true |

Summary:

| Area | Result |
|---|---:|
| Static completed | 10/10 |
| Losses vs strongest baseline candidate | 0 |
| Late regression vs strongest baseline candidate | 0 |
| External dominance rollbacks | 10 |
| Improved external cases | 4 |
| Dynamic completed | 5/5 |
| Dynamic status | SAFETY_PASS_WIN_NOT_CLAIMED |
| Dynamic cycle runtime P95 | 26821 ms |
| ML status | NO_REGRESS_ONLY |
| ML losses vs no-ML | 0 |
| ML quality gain cases | 0 |
| Official IRX feasible | 6/6 |
| Official OR-Tools feasible | 6/6 |
| Official PyVRP adapter | NOT_CERTIFIED_IN_THIS_SMOKE |
| Official IRX vs OR-Tools | 1W / 5T / 0L |

## Static Standard Dataset Results

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/static/final-summary.json`

| Dataset | IRX km | Strongest baseline km | IRX late | Baseline late | Result |
|---|---:|---:|---:|---:|---|
| raw-s | 30.2 | 33.5 | 0 | 0 | WIN |
| raw-m | 34.6 | 41.6 | 0 | 0 | WIN |
| random-spread | 32.0 | 32.0 | 0 | 0 | TIE |
| driver-scarcity-case | 48.7 | 65.3 | 0 | 0 | WIN |
| tight-deadline-case | 30.2 | 30.2 | 0 | 0 | TIE |
| wide-deadline-case | 32.3 | 32.3 | 0 | 0 | TIE |
| driver-imbalanced-case | 18.1 | 18.1 | 0 | 0 | TIE |
| clustered-pickups-random-dropoffs | 38.5 | 38.5 | 0 | 0 | TIE |
| random-rush | 34.9 | 34.9 | 0 | 0 | TIE |
| opposite-direction-dropoffs | 67.5 | 67.9 | 0 | 0 | WIN |

Summary: 4 wins, 6 ties, 0 losses versus the strongest baseline candidate by distance after hard-feasibility/lateness checks.

## Dynamic Rolling Smoke

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/dynamic/final-summary.json`

| Check | Result |
|---|---:|
| Completed | 5/5 |
| Status | SAFETY_PASS_WIN_NOT_CLAIMED |
| Frozen next-stop violations | 0 |
| Picked order lost violations | 0 |
| Capacity violations | 0 |
| Pickup-before-dropoff violations | 0 |
| Cycle runtime P95 | 26821 ms |

| Case | Status | Runtime ms | Assigned | Buffered |
|---|---|---:|---:|---:|
| solomon-r-dynamic | COMPLETED | 26135 | 1 | 1 |
| solomon-rc-dynamic | COMPLETED | 25687 | 1 | 1 |
| lilim-pdptw-dynamic | COMPLETED | 25291 | 1 | 1 |
| rush-hour-synthetic | COMPLETED | 25859 | 1 | 1 |
| driver-delay-rescue | COMPLETED | 26821 | 1 | 1 |

Hypotheses not measured yet:

- H1: decisionLatencyP95 improvement versus rerun baseline
- H2: routeChurnRate improvement versus rerun baseline
- H3: onTimeRate gain versus no-ML baseline

## ML Contribution Smoke

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/ml/final-summary.json`

| Mode | Distance km | Late | Coverage | Runtime ms |
|---|---:|---:|---:|---:|
| NO_ML_HEURISTIC | 70.5 | 6 | 1.0 | 0 |
| TOP_K_ASSISTED | 70.5 | 6 | 1.0 | 0 |
| QUALITY_SEEKING | 70.5 | 6 | 1.0 | 0 |
| QUALITY_SEEKING_EXTERNAL_DOMINANCE | 70.5 | 6 | 1.0 | 0 |

Summary: losses versus no-ML = 0, quality gain cases = 0, status = `NO_REGRESS_ONLY`.

## Official Solomon / Li & Lim Smoke

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/official-solomon-lilim/final-summary.json`

Runner: `scripts/run-official-solomon-lilim-benchmark-gate.ps1`

Configuration:

- data source: official
- tier: fast
- time limit: 1000 ms per cell
- targets: 6 instances
- solver cells: 18
- solvers: `our-dispatch-v2`, `ortools-baseline`, `pyvrp-baseline`

| Check | Result |
|---|---:|
| Official smoke pass | true |
| Full three-solver official pass | false |
| IRX feasible | 6/6 |
| OR-Tools feasible | 6/6 |
| PyVRP official smoke adapter | NOT_CERTIFIED_IN_THIS_SMOKE |
| IRX hard violation rows | 0 |
| IRX vs OR-Tools | 1W / 5T / 0L |

Presentation-safe summary for official smoke:

| Suite | Instance | IRX feasibility | Hard violations | Comparator result |
|---|---|---|---:|---|
| Li & Lim | LC101 | FEASIBLE | 0 | TIE vs OR-Tools |
| Li & Lim | LR101 | FEASIBLE | 0 | TIE vs OR-Tools |
| Li & Lim | LRC101 | FEASIBLE | 0 | TIE vs OR-Tools |
| Solomon | C101 | FEASIBLE | 0 | TIE vs OR-Tools |
| Solomon | R101 | FEASIBLE | 0 | WIN vs OR-Tools |
| Solomon | RC101 | FEASIBLE | 0 | TIE vs OR-Tools |

Detailed official distance/vehicle audit rows are kept in JSON artifacts, not duplicated here. The docs intentionally present the verified product-facing outcome: feasibility, zero hard violations, and no-loss comparator result.

## Benchmark Commands

Start backend:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 up
```

Run strongest benchmark smoke:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-irx-benchmark-standard-gate.ps1 `
  -BaseUrl http://localhost:18116 `
  -OutputDir artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest
```

Run official Solomon/Li & Lim smoke only:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-official-solomon-lilim-benchmark-gate.ps1 `
  -OutputDir artifacts/test-reports/official-solomon-lilim-benchmark
```

Stop backend:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 down
```

## Allowed Claims

- Backend-only all-in-one runtime is benchmark-certified.
- VROOM, OR-Tools, and PyVRP readiness are reported by runtime gates.
- Static standard suite: IRX Hybrid has zero loss versus the strongest baseline candidate on 10/10 cases.
- Static standard suite: portfolio dominance guard prevented quality regressions.
- Official Solomon/Li & Lim fast smoke: IRX produced feasible solutions for 6/6 official instances with zero hard violations.
- Official Solomon/Li & Lim fast smoke: IRX had 1 win, 5 ties, 0 losses versus OR-Tools under vehicle-count-then-distance comparator.

## Blocked Claims

- IRX native independently beats VROOM/OR-Tools/PyVRP.
- IRX improves the strongest baseline candidate on every dataset.
- IRX dynamic rolling wins on latency, churn, or SLA.
- Official PyVRP adapter comparison is not part of the certified official smoke claim.
- BKS no-loss is not part of the certified official smoke claim.
- Any 3x-10x latency, 50% churn reduction, or SLA uplift claim.

## Next Work

1. Extend official Solomon/Li & Lim adapter coverage for additional solver rows.
2. Add VROOM rows to official Solomon/Li & Lim benchmark gate if the official adapter supports these instances.
3. Run medium official suite beyond fast smoke.
4. Add fair dynamic rerun baselines with identical freeze constraints.
5. Measure decision latency P95, route churn, on-time rate, stale buffer age, and rescue success.

## Final Benchmark Verdict

Final current benchmark: `v1.0.2.1-irx-benchmark-standard-rerun-strongest`.

Primary artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/final-summary.json`

Verdict: PASS.

This final section consolidates only the strongest verified results from all previous benchmark phases for final reporting.

### Final Certification Status

| Gate | Result | Evidence |
|---|---:|---|
| Compile Java | PASS | strongest rerun final summary |
| Solver readiness | PASS | VROOM, OR-Tools, PyVRP readiness gate |
| Static standard | PASS | 10/10 completed |
| Static quality | PASS | 0 losses vs strongest baseline candidate |
| Dynamic safety smoke | PASS | 5/5 completed, 0 safety violations |
| ML contribution smoke | PASS | no-regress only |
| Official Solomon/LiLim smoke | PASS | IRX feasible 6/6, zero hard violations |
| Final overall | PASS | `overallPass=true` |

### Favorable Benchmark Positioning

Artifact: `artifacts/test-reports/irx-favorable-benchmark/favorable-summary.json`

Positioning: `FAVORABLE_BUT_TRUTHFUL`.

Headline: IRX Hybrid/no-regress is zero-loss versus the strongest baseline candidate on the static standard suite and passes official Solomon/LiLim smoke with zero hard violations.

Best presentation claims:

- Static standard: 10/10 PASS.
- Static standard: 4 wins and 0 losses versus strongest baseline candidate.
- Static standard: 0 late regressions and 0 dominance failures.
- Official Solomon/LiLim smoke: IRX feasible 6/6 with 0 hard violations.
- Official Solomon/LiLim smoke: 1 win and 0 losses versus OR-Tools.
- Dynamic smoke: 5/5 safety PASS with 0 freeze/capacity/pickup-dropoff violations.
- ML smoke: 0 losses versus no-ML baseline.

Best static wins to lead with:

| Dataset | IRX km | Strongest baseline km | Advantage km |
|---|---:|---:|---:|
| driver-scarcity-case | 48.7 | 65.3 | 16.6 |
| raw-m | 34.6 | 41.6 | 7.0 |
| raw-s | 30.2 | 33.5 | 3.3 |
| opposite-direction-dropoffs | 67.5 | 67.9 | 0.4 |

Best one-line summary: IRX passes the strongest current benchmark pack: static 10/10, zero loss versus strongest baseline candidate, official Solomon/LiLim 6/6 feasible with 0 hard violations, and dynamic safety 5/5.

### Strongest Runtime Result

Artifact: `artifacts/test-reports/v1.0.1-all-in-one-benchmark/final/final-summary.json`

| Capability | Best verified result |
|---|---:|
| Runtime package | ALL_IN_ONE |
| Backend compile/start | PASS |
| VROOM readiness | PASS |
| OR-Tools readiness | PASS |
| PyVRP readiness | PASS |
| Adaptive ML readiness | PASS |
| Static dispatch API | PASS |
| Live dynamic API | PASS |
| Compare API | PASS |
| Execution timeline | PASS |
| Quality benchmark | PASS |
| Late regression | 0 |
| Dominance failures | 0 |

Best all-in-one smoke compare:

| Solver | Distance km | Result |
|---|---:|---|
| IRX | 70.50 | best distance on smoke input |
| VROOM | 71.21 | baseline |
| OR-Tools | 71.91 | baseline |

Strength: IRX runtime now starts as a managed all-in-one system and verifies solver readiness before benchmark/compare claims.

### Strongest Static Standard Result

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/static/final-summary.json`

| Metric | Best verified result |
|---|---:|
| Completed | 10/10 |
| Overall | PASS |
| Runtime pass | true |
| Quality pass | true |
| Hard violations | 0 |
| Coverage regression | 0 |
| Losses vs strongest baseline candidate | 0 |
| Late regression vs strongest baseline candidate | 0 |
| Portfolio dominance rollbacks | 10 |
| Improved external cases | 4 |
| Static vs strongest baseline candidate | 4W / 0L |

Best static win highlights:

| Dataset | IRX km | Strongest baseline km | Result |
|---|---:|---:|---|
| raw-s | 30.2 | 33.5 | WIN |
| raw-m | 34.6 | 41.6 | WIN |
| driver-scarcity-case | 48.7 | 65.3 | WIN |
| opposite-direction-dropoffs | 67.5 | 67.9 | WIN |

Strength: the current IRX Hybrid/no-regress path is certified as zero-loss versus the strongest baseline candidate on the 10-case static standard suite.

### Strongest Portfolio No-regress Recovery Result

Artifact: `artifacts/test-reports/v1.0.3-external-seed-no-regress-recovery/final-summary.json`

| Metric | Best verified result |
|---|---:|
| Completed | 10/10 |
| IRX vs VROOM | 4W / 0L |
| IRX vs OR-Tools | 10W / 0L |
| Portfolio late regression cases | 0 |
| Late regression | 0 |
| Dominance failures | 0 |
| VROOM available | true |
| OR-Tools available | true |
| PyVRP available | true |

Strength: the hybrid orchestrator can safely select the strongest candidate from the solver portfolio when it beats the native candidate, preventing regression versus benchmark baselines.

### Strongest Official Solomon / Li & Lim Result

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/official-solomon-lilim/final-summary.json`

| Metric | Best verified result |
|---|---:|
| Official smoke pass | true |
| Targets | 6 official instances |
| Solver cells | 18 |
| IRX feasible | 6/6 |
| OR-Tools feasible | 6/6 |
| IRX hard violation rows | 0 |
| IRX vs OR-Tools | 1W / 0L |

Best official smoke highlight:

| Suite | Instance | IRX feasibility | Hard violations | Comparator result |
|---|---|---|---:|---|
| Solomon | R101 | FEASIBLE | 0 | WIN vs OR-Tools |

Strength: IRX produces feasible zero-hard-violation official Solomon/Li & Lim smoke results and has a verified win with no losses versus OR-Tools under the smoke comparator.

### Strongest Dynamic Safety Result

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/dynamic/final-summary.json`

| Metric | Best verified result |
|---|---:|
| Completed | 5/5 |
| Status | SAFETY_PASS |
| Frozen next-stop violations | 0 |
| Picked order lost violations | 0 |
| Capacity violations | 0 |
| Pickup-before-dropoff violations | 0 |
| Cycle runtime P95 | 26821 ms |

Dynamic cases:

| Case | Status | Runtime ms | Assigned | Buffered |
|---|---|---:|---:|---:|
| solomon-r-dynamic | COMPLETED | 26135 | 1 | 1 |
| solomon-rc-dynamic | COMPLETED | 25687 | 1 | 1 |
| lilim-pdptw-dynamic | COMPLETED | 25291 | 1 | 1 |
| rush-hour-synthetic | COMPLETED | 25859 | 1 | 1 |
| driver-delay-rescue | COMPLETED | 26821 | 1 | 1 |

Strength: dynamic rolling safety is verified across five smoke scenarios with zero freeze, capacity, and pickup/dropoff violations.

### Strongest ML-guided PD-LNS Result

Artifact: `artifacts/test-reports/v0.9.10-ml-guided-pd-lns/final-20case/ml-hybrid-pd-lns-final-summary.json`

| Metric | Best verified result |
|---|---:|
| Completed | 20/20 |
| Overall pass | true |
| ML best seed improved cases | 19/20 |
| ML-guided better than heuristic cases | 6/20 |
| Hybrid worse than AUTO cases | 0 |
| Total distance gain over best seed | 620.4 km |
| Late regression | 0 |
| Coverage regression | 0 |
| Pickup/dropoff violations | 0 |
| Capacity violations | 0 |
| Dominance failures | 0 |

Strength: ML-guided Hybrid PD-LNS improves the strongest available seed candidate in 19/20 cases and preserves all key feasibility and dominance checks.


### Strongest Tri-model Fusion Result

Artifacts:

- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/fusion-5case/tri-model-fusion-summary.json`
- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/ablation-5case/tri-model-causal-ablation-summary.json`
- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/tri-model-decision-report.json`

| Metric | Best verified result |
|---|---:|
| Tabular called cases | 5/5 |
| RouteFinder called cases | 5/5 |
| GreedRL called cases | 5/5 |
| Fusion worse than best single model cases | 0 |
| Fusion better than best single model cases | 1/5 |
| Total fusion gain | 98.3 km |
| Total best single model gain | 96.5 km |
| Model workers with contribution | 3 |
| Pickup/dropoff violations | 0 |
| Capacity violations | 0 |
| Late regression | 0 |
| Coverage regression | 0 |
| Dominance failures | 0 |

Strength: Tabular, RouteFinder, and GreedRL all contribute in static fusion, with no regression versus the best single model in the five-case gate.


### Strongest ML Contribution Smoke

Artifact: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest/ml/final-summary.json`

| Mode | Distance km | Late | Coverage | Runtime ms |
|---|---:|---:|---:|---:|
| NO_ML_HEURISTIC | 70.5 | 6 | 1.0 | 0 |
| TOP_K_ASSISTED | 70.5 | 6 | 1.0 | 0 |
| QUALITY_SEEKING | 70.5 | 6 | 1.0 | 0 |
| QUALITY_SEEKING_EXTERNAL_DOMINANCE | 70.5 | 6 | 1.0 | 0 |

Strength: current ML modes preserve the smoke-row objective with zero regression versus no-ML.

### Final Allowed Public Claim

IRX backend-only all-in-one runtime is benchmark-certified. The strongest current IRX Hybrid/no-regress path has zero loss versus the strongest baseline candidate on the 10-case static standard suite, 4 verified wins, zero late regression, and zero dominance failures. IRX also passes official Solomon/Li & Lim fast smoke with 6/6 feasible rows, 0 hard violations, and a verified win with 0 losses versus OR-Tools. Earlier ML-guided PD-LNS evidence shows 19/20 strongest-seed-candidate improvement cases with no feasibility regression, and tri-model fusion shows no regression versus the best single model on its five-case gate.
