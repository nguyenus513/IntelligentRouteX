# IRX Production Documentation

This directory contains the canonical documentation set for IntelligentRouteX v1.0 preparation. Older milestone-specific notes were consolidated into the documents below so that the project is easier to run, review, defend, and maintain.

## Read order

1. `SYSTEM_OVERVIEW.md` — current system status, features, certified milestones, and claim boundaries.
2. `ARCHITECTURE.md` — backend, runtime, optimizer, Adaptive ML, BigData-lite, API, Playground, and package architecture.
3. `API_REFERENCE.md` — locked API v1 groups, envelopes, job lifecycle, static/live/rescue/BigData/artifact/event/runtime contracts.
4. `API_EXAMPLES.md` — PowerShell examples for health, static jobs, live cycles, rescue, BigData-lite, artifacts, events, and one-click test.
5. `BIGDATA_LITE_API.md` — large-input flow without Kafka/Spark: ingest, normalize, queue, worker, paginate, artifacts, stream, DLQ, requeue.
6. `ADAPTIVE_ML_POLICY.md` — ML role, evidence, accepted claims, safety guards, and future work.
7. `BENCHMARKS.md` — benchmark methodology, final certified numbers, and how to interpret objective wins.
8. `OPERATIONS.md` — one-click start, status, quick test, shutdown, package, Docker, and troubleshooting.
9. `PLAYGROUND.md` — one-screen demo behavior and panel structure.
10. `RELEASE.md` — release package, tags, artifacts, generated ZIP policy, and final checklist.
11. `THESIS_GUIDE.md` — suggested Java thesis/report structure.
12. `openapi/irx-api-v1.yaml` — OpenAPI v1 contract marker used by API gate.

## Current release line

- Latest closed milestone: `v0.9.9.6-one-click-start`.
- Latest API contract: `v0.9.9.4-api-contract-final`.
- Latest Playground milestone: `v0.9.9.5-irx-playground`.
- Latest BigData-lite API milestone: `v0.9.9.3-bigdata-lite-api`.
- Latest Adaptive ML quality milestone: `v0.9.9-adaptive-ml-quality-seeking`.

## Core commands

```powershell
.\scripts\irx.ps1 up
.\scripts\irx.ps1 status
.\scripts\irx.ps1 test -Quick
.\scripts\irx.ps1 down
.\scripts\irx.ps1 package
```

## Claim boundary

IRX is a Java dispatch optimization system with Adaptive ML policy. ML is used to control search policy: move ordering, TOP-K assisted evaluation, and quality-seeking budget expansion. ML does not replace the external solvers. VROOM, PyVRP, OR-Tools, Distance, IRX Native, and RouteFinder-refined proposals are treated as seed/contributor sources; final output remains `IRX_ML_FUSED_HYBRID` and is protected by hard validators and dominance guards.
