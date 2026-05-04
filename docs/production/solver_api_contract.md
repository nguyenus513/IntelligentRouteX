# Phase 78 Solver API Contract

This document defines the future production/shadow-mode API boundary around Phase 56F or a later certified runner.

## Request

Input is one `live-dispatch-snapshot/v1` object defined in `docs/production/live_snapshot_schema.md`.

The solver must treat the request as immutable audit evidence:

- do not mutate the input snapshot;
- record `snapshotId`, `region`, and `timestamp` in diagnostics;
- record the exact solver runner and deterministic seed;
- do not use VROOM, BKS, or comparator outputs inside the production solver path.

## Response

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `schemaVersion` | string | Use `live-dispatch-solver-response/v1`. |
| `snapshotId` | string | Echo from request. |
| `solver` | string | Solver id, e.g. `phase56f-stable-certification`. |
| `mode` | string | `shadow`, `canary`, or future `main`. |
| `assignments` | array | Driver/order assignments. |
| `routeSequences` | array | Ordered pickup/dropoff route per driver. |
| `acceptedOrders` | array | Orders included in the solution. |
| `rejectedOrders` | array | Orders not assigned, with reasons. |
| `fallbackReason` | string/null | Set when fallback output is returned. |
| `runtimeMs` | number | Wall-clock runtime. |
| `violations` | array | Hard/soft violations detected by checker. |
| `diagnostics` | object | Scorecard, budget, signatures, and stage trace. |

## Assignment Record

Each assignment should include:

- `driverId`
- `orderId`
- `pickupEta`
- `dropoffEta`
- `sequenceIndexPickup`
- `sequenceIndexDropoff`

## Response Invariants

- No hard violation may be accepted in production-main.
- Objective regression must be logged and rejected unless fallback explicitly preserves current active routes.
- If `runtimeMs` exceeds budget, response must set `fallbackReason`.
- Shadow mode must never alter live dispatch decisions.

## Current Status

The repository currently supports benchmark/shadow-mode certification. It does **not** claim production-main readiness until live adapter, fallback/canary policy, replay evidence, monitoring, and SLA dashboards are complete.
