# Phase 74 Final Comprehensive System Report

## Executive Summary

IntelligentRouteX is currently CERTIFICATION_SAFE and a PRODUCTION_CANDIDATE for synthetic feasibility/shadow-mode evaluation, but not PRODUCTION_MAIN_READY.

## System Architecture

Stable optimizer: Phase 56F. Research baseline: Phase 47. Industry comparator: VROOM. Feasibility oracle: internal checker.

## Dataset Matrix

# Phase 69 Dataset Matrix

| Dataset | Type | Scenarios / Instances | Purpose | Expected Bottleneck |
|---|---|---|---|---|
| Li-Lim 8-case | Academic PDPTW | `lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8` | Pickup-delivery, time windows, vehicle-loss regression checks | route-pool budget, vehicle count, distance quality |
| synthetic-food-smoke | Production-like synthetic PDPTW | `lunch_peak`, `rain_peak` | Fast food-dispatch sanity check | time windows, peak/rain traffic |
| synthetic-food-full | Production-like synthetic PDPTW | `lunch_peak`, `dinner_peak`, `apartment_cluster`, `rain_peak`, `sparse_suburban`, `cancellation_risk` | Full synthetic dispatch feasibility/stability evaluation | food-like time windows, clustering, traffic, cancellation risk |
| future real replay logs | Production replay | pending | Validate live orders/drivers/activeRoutes adapter | SLA tail, online churn, fallback behavior |
| future time-dependent traffic | Production stress | pending | Validate traffic-sensitive dispatch | travel-time uncertainty, rain/peak congestion |

Each dataset should be reported with request count, driver count, time-window tightness, traffic multiplier, clustered dropoff ratio, stress flags, and expected bottleneck before production claims are made.

## Baseline Matrix

# Phase 70 Baseline Matrix

| Baseline | Role | Current Status | Interpretation |
|---|---|---|---|
| Phase 56F | Stable certification system | Promoted for certification/shadow-mode | Safety, determinism, hard budget, feasibility baseline |
| Phase 47 | Research-quality baseline | Previous research baseline | Useful quality reference, not strict certification baseline |
| VROOM | Industry / production-like comparator | Active comparator | Strong external baseline; on synthetic food current run has no feasible solution |
| Internal checker | Feasibility oracle | Active | Validates exact coverage, pickup/dropoff, capacity, time windows |
| OR-Tools | Future optional baseline | Not part of current final claim | Useful additional algorithmic comparator |
| PyVRP | Future optional baseline | Not part of current final claim | Useful HGS-style comparator if PDPTW mapping is validated |

Current conclusion:

- Phase 56F wins synthetic food feasibility/stability: feasible `6/6`, hard violations `0`, overBudget `0`.
- VROOM wins some Li-Lim feasible cases on quality.
- Synthetic food quality superiority remains inconclusive because VROOM has no feasible synthetic solution in the audited run.

## Safety Scorecard

# Phase 68 System Scorecard

Gate: **PASS**

## Safety
- Hard violations: 0
- Time-window violations: 0

## Runtime
- Runtime p50/p95/p99 ms: 24252.0 / 25113.0 / 25113.0
- OverBudget count: 0

## Comparator
- VROOM counts: `{"vroom-hard-fail": 6}`
- Gap counts: `{"challenger-better-feasibility": 6}`
- Semantic mismatch count: 2

## Food Dispatch
- Detailed food dispatch metrics are produced by Phase 71.

## Food Dispatch Metrics

# Phase 71 Food Dispatch Metrics

Gate: **PASS**

| Instance | O2D Mean | O2D P95 | Late Rate | Batching | Load Balance |
|---|---:|---:|---:|---:|---:|
| lunch_peak | 10.262832789597402 | 21.05812338827411 | 0.0 | 12.0 | 6 |
| dinner_peak | 12.760366413387876 | 29.915768355335103 | 0.0 | 14.0 | 2 |
| apartment_cluster | 12.219570325083737 | 41.68077125085097 | 0.0 | 13.0 | 2 |
| rain_peak | 14.798584696982942 | 39.287862752669525 | 0.0 | 12.0 | 6 |
| sparse_suburban | 14.799690078953644 | 33.560410116812704 | 0.0 | 18.0 | 0 |
| cancellation_risk | 14.224673972221012 | 31.073327927292212 | 0.0 | 11.0 | 4 |

## Stress Sensitivity

# Phase 72 Stress & Sensitivity Suite

Variant count: 576

| Orders | Drivers | Traffic | TW | Cluster | Expected Failure |
|---:|---|---:|---|---:|---|
| 20 | loose | 1.0 | loose | 0.1 | quality-risk |
| 20 | loose | 1.0 | loose | 0.5 | quality-risk |
| 20 | loose | 1.0 | loose | 0.8 | quality-risk |
| 20 | loose | 1.0 | normal | 0.1 | quality-risk |
| 20 | loose | 1.0 | normal | 0.5 | quality-risk |
| 20 | loose | 1.0 | normal | 0.8 | quality-risk |
| 20 | loose | 1.0 | tight | 0.1 | quality-risk |
| 20 | loose | 1.0 | tight | 0.5 | quality-risk |
| 20 | loose | 1.0 | tight | 0.8 | quality-risk |
| 20 | loose | 1.0 | extreme | 0.1 | quality-risk |
| 20 | loose | 1.0 | extreme | 0.5 | quality-risk |
| 20 | loose | 1.0 | extreme | 0.8 | quality-risk |
| 20 | loose | 1.2 | loose | 0.1 | quality-risk |
| 20 | loose | 1.2 | loose | 0.5 | quality-risk |
| 20 | loose | 1.2 | loose | 0.8 | quality-risk |
| 20 | loose | 1.2 | normal | 0.1 | quality-risk |
| 20 | loose | 1.2 | normal | 0.5 | quality-risk |
| 20 | loose | 1.2 | normal | 0.8 | quality-risk |
| 20 | loose | 1.2 | tight | 0.1 | quality-risk |
| 20 | loose | 1.2 | tight | 0.5 | quality-risk |

## Ablation Study

# Phase 73 Ablation Study

| Config | Quality Effect | Runtime Risk | Stability Effect |
|---|---|---|---|
| base-incumbent-only | baseline feasible construction | low | medium |
| + internal solver generator | candidate diversity and objective improvement | medium | requires deterministic candidate selection |
| + route-pool | vehicle/distance improvements when budget permits | high without hard cap | requires route-pool reserve and replay |
| + stable replay | no direct quality gain | low | high |
| + hard budget guard | may skip expensive improvements | low | high |
| + synthetic integration | food-like feasibility evidence | medium | dataset-dependent |

Conclusion: Phase 56F stability comes from stable replay plus hard budget guard; route-pool can improve quality but is a runtime-risk component without caps.

## VROOM Comparison

# Synthetic Food Result Interpretation

This note explains how to interpret the synthetic food VROOM comparison without overstating the result.

## Feasibility Win Vs Quality Win

A **feasibility/stability win** means a solver returns routes that satisfy hard constraints:

- exact pickup/dropoff coverage;
- pickup before dropoff;
- capacity constraints;
- time windows;
- wall-clock budget.

A **quality win** requires both solvers to be feasible first. Only then should vehicle count, distance, and objective be compared.

In the current synthetic-food full run, Phase 56F is feasible `6/6`, while VROOM hard-fails `6/6`. Therefore the correct conclusion is feasibility/stability advantage for Phase 56F; distance or vehicle-count quality remains inconclusive.

## Why VROOM Hard-Fail Is Not A Distance Comparison

When VROOM returns a route with time-window violations, its shorter distance or equal vehicle count is not a valid quality win. Infeasible routes are rejected before distance and vehicle count are considered.

Phase 59 classifies these cases as `challenger-better-feasibility`, not `challenger-quality-win-distance` or `challenger-quality-win-vehicle-count`.

## Why Matrix-Duration Mismatch Is Separate

Phase 67B separates confirmed VROOM time-window violations from semantic mismatches:

- `vroom-true-time-window-violation`: VROOM step arrivals are outside the internal node time windows.
- `matrix-duration-mismatch`: distance and duration semantics disagree enough that the comparator needs separate interpretation.

The current audit-backed result is:

| Classification | Count |
|---|---:|
| vroom-true-time-window-violation | 4/6 |
| matrix-duration-mismatch | 2/6 |
| unknown | 0/6 |

The two matrix-duration mismatch cases should not be described as confirmed true VROOM solver failures. They should be described as comparator semantics cases that require aligned distance/duration interpretation before quality scoring.

## Recommended Wording

Use this wording:

> On synthetic food scenarios, Phase 56F produces feasible routes for all six cases with hard violations `0` and overBudget `0`. VROOM returns no internally feasible solution in this run; Phase 67B confirms four true VROOM time-window violations and two matrix-duration semantic mismatches. This supports a feasibility/stability advantage for IntelligentRouteX on this synthetic suite. Quality superiority remains inconclusive because VROOM has no feasible synthetic solution for distance or vehicle-count comparison.

## Phase 76 VROOM Capability Micro-Suite

Phase 76 verifies VROOM and Phase 56F on 15 capability micro-tests. Both solvers are feasible `15/15`; semantic audit is `PASS`.

| Metric | Result |
|---|---:|
| both-feasible | 15/15 |
| fair quality tie | 10 |
| Phase 56F distance wins | 5 |
| VROOM distance wins | 0 |

Phase 76 shows that VROOM supports core optimizer capabilities such as shipment bundling, driver/vehicle assignment, pickup-delivery precedence, capacity, time windows, waiting, service time, skill matching, shift windows, breaks, open route, priority, custom/asymmetric matrix, and multi-driver load balancing. It also shows Phase 56F is competitive when both solvers are feasible on micro-capability cases.

## Known Limitations

No live production adapter, no fallback/canary policy, no real replay logs, and synthetic quality vs VROOM is inconclusive when VROOM is infeasible.

## Production Readiness Verdict

Current verdict: CERTIFICATION_SAFE / PRODUCTION_CANDIDATE for synthetic feasibility. Not PRODUCTION_MAIN_READY.
