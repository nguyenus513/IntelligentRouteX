# Phase 78 Fallback And Rollback Policy

This policy defines when IntelligentRouteX must avoid applying a new route plan and instead preserve existing dispatch behavior.

## Fallback Triggers

Fallback is mandatory when any of these occur:

- solver timeout or wall-clock overBudget;
- hard violation in candidate solution;
- missing or invalid `durationMatrix`;
- missing `activeRoutes` in the live snapshot;
- unknown node referenced by order, driver, or route;
- infeasible pickup/dropoff coverage;
- capacity violation;
- time-window violation;
- objective regression accepted by mistake;
- internal checker unavailable;
- live adapter schema validation failure.

## Fallback Output

Fallback response must include:

- `fallbackReason`;
- original `snapshotId`;
- preserved active routes where available;
- runtime and validation diagnostics;
- `violations` explaining why optimization was not applied.

## Rollback

Rollback must be possible for canary/shadow-to-main rollout:

- keep previous production dispatch output;
- keep solver response and checker diagnostics;
- record the diff between production output and candidate output;
- automatically disable candidate solver on hard violations, timeout spikes, or SLA regressions.

## Current Status

Fallback/rollback is specified here but not yet wired into a live production dispatcher. Until it is implemented and tested with replay/canary evidence, the system must not be marked `PRODUCTION_MAIN_READY`.
