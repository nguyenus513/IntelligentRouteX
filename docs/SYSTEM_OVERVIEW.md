# System Overview

IntelligentRouteX is a Java/Spring Boot route dispatch system with a React dashboard and API-first runtime. The current repository state is certified for local production-demo use through one-click scripts, API gates, Playground gates, BigData-lite gates, and benchmark evidence.

## Certified capabilities

| Area | Evidence |
|---|---|
| One-click startup/test/package | `v0.9.9.6-one-click-start`, `overallPass=true` |
| Playground | `/playground` route, static/live/rescue/BigData flows PASS |
| API contract | response/error envelope, job lifecycle, static/live/rescue/BigData, artifacts, events, metrics PASS |
| BigData-lite | batch ingest, normalization, idempotency, queue routing, backpressure, pagination, artifacts, event log/stream, dead-letter, telemetry coalescing PASS |
| Production runtime MVP | stores, queue routing, async worker facade, rate limit, artifact guard, observability, Docker compose smoke PASS |
| Adaptive ML quality seeking | `20/20` completed, `2` improved cases, `1.6 km` total distance gain, `0` loss/late/dominance/coverage regressions |
| Final certification baseline | FAST `7/7`, quality `20/20`, live stress `4` cycles, rescue late-not-worse PASS |

## What starts in local mode

`./scripts/irx.ps1 up` starts:

1. Spring Boot backend on `http://localhost:18116`.
2. Vite dashboard on `http://localhost:5173`.
3. Playground route at `http://localhost:5173/playground`.
4. Runtime health checks for `/api/v1/health` and `/playground`.

## Dispatch modes

- `STATIC_DISPATCH`: asynchronous route optimization job and result retrieval.
- `LIVE_ROLLING`: rolling cycle demo with order buffering and driver telemetry.
- `RESCUE`: disruption/recovery job with safety guard evidence.
- `BIGDATA_LITE`: batch ingest and paginated output for larger API payloads.

## Optimization pipeline

The optimizer combines internal heuristic search, seed contributors, external solver evidence when available, Adaptive ML policy ordering, evaluator accept/reject logic, and dominance safety guards. The final solver invariant in certification evidence is `IRX_ML_FUSED_HYBRID`.

## Adaptive ML role

Adaptive ML is a policy layer. It ranks seeds/operators/move candidates and adjusts search budget. It does not replace VROOM/PyVRP and does not bypass evaluator or dominance guards.

## Claim boundaries

- This is a local production-demo MVP, not a multi-node cloud deployment.
- BigData-lite is lightweight batch/queue/runtime handling, not Kafka/Spark processing.
- Solver quality claims are limited to committed evidence suites.
- External solver evidence records VROOM as `EVIDENCE_GAP` in final certification when local evidence is unavailable.
