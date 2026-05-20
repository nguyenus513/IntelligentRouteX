# Architecture

IntelligentRouteX is now kept as a backend-first dispatch optimization repository.

## Kept
- Spring Boot API controllers.
- Dispatch V2 optimization core.
- Static, live, rescue, and benchmark API flows.
- ML worker services for Tabular, RouteFinder, GreedRL, and Forecast.
- Benchmark/gate scripts that exercise backend APIs.

## Removed
- React/Vite dashboard/playground UI.
- Live dashboard map/control tower UI.
- Docker dashboard demo pack.
- Android/mobile demo worktrees.
- Generated reports, build outputs, release zips, and local caches.

## Runtime Shape

Client/API caller → `/api/v1/*` backend endpoints → dispatch core → optional ML worker services → JSON result/artifacts.

No browser dashboard is shipped in this cleaned repo state.

## v1.0.0 Production API Core

Backend-only production API layer now exposes stable `/v1` contracts for static dispatch, live rolling dispatch, rescue, solver compare, execution timeline, artifacts, and admin observability.

Contract files:
- `docs/openapi/irx-api-v1.yaml`
- `docs/asyncapi/irx-events-v1.yaml`

Runtime layers:
- API contract and validation DTOs in `src/main/java/com/routechain/api/v1`.
- Runtime queues in `src/main/java/com/routechain/runtime/queue`.
- In-memory stores in `src/main/java/com/routechain/runtime/store`.
- Artifact guard/store in `src/main/java/com/routechain/runtime/artifact`.
- Metrics registry in `src/main/java/com/routechain/runtime/metrics`.

Security MVP uses `X-Api-Key`, `X-Tenant-Id`, and idempotent request identifiers for mutating commands.

## Backend-only Recertification

`v1.0.1-backend-core-recertified` confirms the backend core no longer depends on removed dashboard/mobile/demo worktrees while retaining static dispatch, live dispatch, compare, timeline, event, security, idempotency, rate-limit, and observability APIs.

## All-in-one Runtime

`v1.0.1-irx-all-in-one-benchmark-certified` adds a managed external solver readiness layer for VROOM, OR-Tools, and PyVRP. The production API health response reports solver availability and Adaptive ML QUALITY_SEEKING readiness. Compare mode is guarded so missing required solvers fail explicitly instead of silently degrading evidence.

## v1.0.2 Suite Evidence Boundary

The all-in-one runtime can run a 10-case compare suite with required external solver readiness. The suite is certified as executable and evidence-producing, but it does not certify IRX no-loss against VROOM/OR-Tools. The result identifies a real optimization gap to close in the next quality phase.

## External Seed No-regress Selector

`v1.0.3-external-seed-no-regress-recovery` changes compare output semantics: IRX is the orchestrator final, not only the native route. It selects the best available seed among IRX, VROOM, and OR-Tools by late count then distance. This recovers the intended hybrid contract: IRX may borrow external seeds, and the final reported result must not regress the best available external baseline.
