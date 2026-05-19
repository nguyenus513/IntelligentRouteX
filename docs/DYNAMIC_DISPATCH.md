# Dynamic Dispatch

## v0.9.11 Dynamic ML Dispatch

Status: backend certification in progress for `v0.9.11-dynamic-ml-dispatch-final`.

IRX supports dynamic live dispatch through backend APIs that accept live orders, driver telemetry, cycle execution, rescue execution, state reads, and event stream reads.

Core backend flow:

1. Live orders enter `/api/v1/live/jobs/{jobId}/orders`.
2. Driver telemetry updates enter `/api/v1/live/jobs/{jobId}/drivers/{driverId}/telemetry`.
3. Freeze policy preserves active/current stops.
4. Forecast risk diagnostics participate in live cycles.
5. GreedRL selects live actions such as `RESCUE_REOPTIMIZE` or `REBALANCE_REPAIR`.
6. Tri-model repair diagnostics record Tabular scoring, RouteFinder candidates, and accepted ML mutations.
7. Safety diagnostics track frozen stop, pickup/dropoff, capacity, late, coverage, and dominance regressions.
8. Events expose order, telemetry, forecast, GreedRL, route repair, freeze, and completion milestones.

Certification artifacts live under `artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/`.

