# IntelligentRouteX

IntelligentRouteX, or IRX, is a Java dispatch optimization system for grouped delivery routing. It combines external seed solvers, an IRX hybrid optimizer, adaptive ML policy, a production-style runtime API, BigData-lite batch ingestion, and a one-screen Playground demo.

Current certified milestone: `v0.9.9.6-one-click-start`.

## What IRX includes

- Java backend with API v1 contracts.
- Static dispatch, live rolling dispatch, rescue dispatch, and freeze-safe runtime behavior.
- Hybrid seed archive using Distance, OR-Tools, VROOM, PyVRP, IRX Native, and RouteFinder-refined proposals.
- Adaptive ML policy for move ordering, TOP-K assisted evaluation, and quality-seeking search.
- BigData-lite API for batch ingest, normalization, queue routing, backpressure, pagination, dead-letter, requeue, artifacts, events, and runtime metrics.
- `/playground` frontend route for one-screen demo: static/live/rescue/BigData flows, baseline comparison, Adaptive ML diagnostics, events, artifacts, and raw JSON.
- One-click local launcher and package command through `scripts/irx.ps1`.

## One-click usage

```powershell
.\scripts\irx.ps1 up
.\scripts\irx.ps1 status
.\scripts\irx.ps1 test -Quick
.\scripts\irx.ps1 down
.\scripts\irx.ps1 package
```

Default URLs:

- Backend: `http://localhost:18116`
- Playground: `http://localhost:5173/playground`
- API health: `http://localhost:18116/api/v1/health`

## Main docs

Start here:

- `docs/README.md` — documentation index.
- `docs/SYSTEM_OVERVIEW.md` — system capabilities and current status.
- `docs/ARCHITECTURE.md` — backend, runtime, optimizer, API, and Playground architecture.
- `docs/API_REFERENCE.md` — API v1 contract.
- `docs/API_EXAMPLES.md` — runnable PowerShell examples.
- `docs/BIGDATA_LITE_API.md` — BigData-lite runtime contract.
- `docs/ADAPTIVE_ML_POLICY.md` — ML role, evidence, and claim boundaries.
- `docs/BENCHMARKS.md` — benchmark methodology and certified numbers.
- `docs/OPERATIONS.md` — local run, test, stop, package, and troubleshooting.
- `docs/PLAYGROUND.md` — Playground flow and panels.
- `docs/RELEASE.md` — packaging and release policy.
- `docs/THESIS_GUIDE.md` — suggested thesis/report structure.

## Claim boundary

IRX does not claim that ML replaces VROOM or PyVRP. External solvers provide strong seeds. IRX uses Adaptive ML as a policy layer to order moves, control TOP-K assisted evaluation, and run quality-seeking search while hard validators and dominance guards remain the final authority.

## Generated release

`release/irx-v1.0.zip` is produced locally by:

```powershell
.\scripts\irx.ps1 package
```

The ZIP is intentionally not committed when it exceeds GitHub size limits. The committed release evidence is the package summary under `artifacts/test-reports/v0.9.9.6-one-click-start/release-summary.json`.
