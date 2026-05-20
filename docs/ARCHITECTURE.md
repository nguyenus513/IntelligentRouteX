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
