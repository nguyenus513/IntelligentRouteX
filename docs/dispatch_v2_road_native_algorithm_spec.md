# Dispatch V2 Road-Native Algorithm Spec

## Goal

The Real Road Dispatch Optimization Rail moves Dispatch V2 from synthetic or straight-line biased routing toward road-native dispatch. Road-native means the system uses snapped road points, real route geometry, routing matrices, feasible pickup/dropoff sequencing, road-quality gates, OR-Tools global selection, repair, and visual evidence rendered from route polylines.

This spec is intentionally incremental. Each loop must produce artifacts and a PASS/PASS_WITH_LIMITS/EVIDENCE_GAP/FAIL verdict before the next loop runs.

## Non-Negotiable Runtime Constraints

- Keep the existing 12-stage Dispatch V2 order intact.
- Do not break replay, harvest, decision-stage, adaptive-compute, or worker-audit contracts.
- Do not treat straight-line distance as selected-route truth when a routing provider is ready.
- Synthetic fallback is allowed only with an explicit fallback reason and lower confidence/verdict.
- Route dominance must not prune across drivers. A route can dominate another only when the same driver and same order set are compared.
- `selectedSingleOrderCount = 0` is a visual/demo target for dense 20 orders / 5 drivers, not a global invariant.

## Existing Repo Capabilities

Current repo already has several Loop 1 foundations:

- `RoutingProvider` with `snap` and `route` methods.
- `HttpOsrmRoutingProvider` using OSRM `/nearest` and `/route`.
- `RoutingSnapResult` and `RoutingRouteResult` models.
- `LegRouteVector.polyline` and routing metadata fields.
- `OsrmTableClient` and `DurationMatrix` foundations.
- `PickupDeliveryPermutationOptimizer` foundation for pickup-before-dropoff route sequences.
- Visual evidence script that renders selected route paths from route-vector artifacts.
- Selector fixes preventing cross-driver dominance pruning.

## Loop Definitions

### Loop 1: Routing Provider, Snap-To-Road, Real Polyline Visual

Purpose: prove selected route geometry is road-native when OSRM is available.

Inputs:
- Standard comparison benchmark artifact.
- Visual evidence artifact.
- Route vector feedback artifacts.

Metrics:
- `snapSuccessRate`
- `selectedBadGeoPointCount`
- `roadRouteCoverage`
- `syntheticFallbackRouteCount`
- `selectedRoutePolylineCoverage`
- `visualStraightLineSelectedRouteCount`
- `executedAssignmentCount`
- `coveredOrderCount`

PASS gate:
- `snapSuccessRate >= 0.95`
- `roadRouteCoverage >= 0.95`
- all selected visual routes have a polyline when provider is ready
- `visualStraightLineSelectedRouteCount = 0` when provider is ready
- `executedAssignmentCount > 0`

### Loop 2: Road-Aware Generator

Purpose: create orders and drivers from routable road-native points, not arbitrary lat/lon scatter.

Required implementation before PASS:
- road-aware order/driver generator
- generator rejection metrics
- routability verification

### Loop 3: OSRM Table Matrix + Cache

Purpose: centralize road-duration matrix for driver/pickup/dropoff scoring.

Required implementation before PASS:
- matrix coverage metrics for selected routes
- cache hit/miss metrics
- latency budget integration

### Loop 4: Road-Native Pickup/Dropoff Sequence Optimizer

Purpose: choose feasible pickup/dropoff sequence using road matrix and freshness/delay constraints.

Required implementation before PASS:
- sequence evaluation counts
- pickup-before-dropoff validation for selected bundles
- rejected sequence reasons

### Loop 5: Road Route Quality Classifier + Dominance Gate

Purpose: classify and reject bad road routes before selector.

Required implementation before PASS:
- network detour ratio
- turns per km
- backtrack score
- road verdicts and hard reject reasons
- dominance scoped to same driver + same order-set

### Loop 6: OR-Tools Road-Native Objective

Purpose: make global set packing optimize coverage and road quality together.

Required implementation before PASS:
- coverage-first scarce bundling remains active
- selected road quality improves or coverage is preserved
- OR-Tools regression tests pass

### Loop 7: Road-Aware Selected Plan Repair

Purpose: repair weak selected plans without reducing coverage or execution count.

Required implementation before PASS:
- repair move generator
- repair evaluator
- repair action logging

### Loop 8: Visual Road Evidence + Closure Matrix

Purpose: produce closure report with visual proof and benchmark matrix.

Required implementation before final PASS:
- selected route cards with routing truth class
- road-vs-straight-line toggles or equivalent visual evidence
- `final_closure_report.md` with `FINAL_VERDICT = PASS`

## State Machine

The rail orchestrator writes:

- `rail_state.json`
- `loop-XX/loop_manifest.json`
- `loop-XX/metrics.json`
- `loop-XX/routePlanQualityLoopReport.md`

The orchestrator auto-advances only on `PASS`. It stops on `PASS_WITH_LIMITS`, `EVIDENCE_GAP`, or `FAIL` and records blockers.

## Current Production Readiness Interpretation

A single Loop PASS does not mean production-ready. Production readiness requires Loop 8 closure with the full matrix and no selected synthetic fallback route when OSRM is ready.
