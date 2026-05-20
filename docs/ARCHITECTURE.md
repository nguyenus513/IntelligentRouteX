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
