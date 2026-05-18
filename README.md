# IntelligentRouteX

IntelligentRouteX (IRX) is a Java/Spring Boot dispatch optimization platform with a React Playground, an API-first runtime, BigData-lite batch handling, and an Adaptive ML policy layer for search guidance.

Current certified milestone: `v0.9.9.7-production-docs-rewrite`.

## What is included

- Static dispatch API and async job lifecycle.
- Live rolling dispatch demo API.
- Rescue dispatch API with late-not-worse and dominance guard evidence.
- BigData-lite batch ingest, validation, queueing, pagination, backpressure, dead-letter, and metrics.
- Adaptive ML policy modes: `TOP_K_ASSISTED` and `QUALITY_SEEKING`.
- Browser Playground at `/playground` for static/live/rescue/BigData demos.
- One-click local launcher and release package builder.

## One-click usage

```powershell
.\scripts\irx.ps1 up
.\scripts\irx.ps1 status
.\scripts\irx.ps1 test -Quick
.\scripts\irx.ps1 down
.\scripts\irx.ps1 package
```

URLs:

- Backend: `http://localhost:18116`
- Playground: `http://localhost:5173/playground`
- API health: `http://localhost:18116/api/v1/health`

## Documentation

Start with `docs/README.md`.

Key docs:

- `docs/SYSTEM_OVERVIEW.md`
- `docs/ARCHITECTURE.md`
- `docs/API_REFERENCE.md`
- `docs/API_EXAMPLES.md`
- `docs/BIGDATA_LITE_API.md`
- `docs/ADAPTIVE_ML_POLICY.md`
- `docs/BENCHMARKS.md`
- `docs/OPERATIONS.md`
- `docs/PLAYGROUND.md`
- `docs/RELEASE.md`
- `docs/THESIS_GUIDE.md`

## Evidence boundary

IRX is certified as a production-demo MVP in this repository. It is not claimed as a distributed production system, a guaranteed global optimum solver, or a replacement for external solvers. All claims in the docs point to committed gate artifacts under `artifacts/test-reports/`.

Large generated release zips are not committed. Rebuild locally with `./scripts/irx.ps1 package`.
