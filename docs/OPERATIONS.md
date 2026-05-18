# Operations

## Requirements

- Windows PowerShell.
- Java 21.
- Node.js and npm.
- Optional VROOM wrapper at `tools/vroom/vroom-wsl.cmd`.
- Local ports `18116` and `5173` free.

## Start local system

```powershell
.\scripts\irx.ps1 up -Profile local
```

This starts backend and dashboard, waits for health, then opens the Playground.

## Status

```powershell
.\scripts\irx.ps1 status
```

Reports backend/dashboard URLs, health, PID, queue, workers, and artifacts.

## Quick test

```powershell
.\scripts\irx.ps1 test -Quick
```

Runs compile, dashboard typecheck/build, API contract gate, Playground gate, and BigData-lite gate. Summary path:

`artifacts/test-reports/v0.9.9.6-one-click-start/one-click-system-summary.json`

## Shutdown

```powershell
.\scripts\irx.ps1 down
```

Stops PID-tracked backend/dashboard processes and clears stale ports.

## Package

```powershell
.\scripts\irx.ps1 package
```

Builds backend jar, dashboard dist, scripts, docs, sample reports, and `release/irx-v1.0.zip`.

## Docker smoke

Docker Compose files exist for smoke/demo packaging. Full cloud deployment is out of scope for the current production-demo MVP.

## Troubleshooting

- Backend fails: inspect `.runtime/backend.log`, check Java 21 and port `18116`.
- Dashboard fails: inspect `.runtime/dashboard.log`, run `npm install` if dependencies are missing, check port `5173`.
- API contract fails: run `scripts/run-irx-api-contract-gate.ps1` directly.
- Playground fails: run `scripts/run-irx-playground-gate.ps1` directly.
- BigData-lite fails: run `scripts/run-irx-bigdata-lite-api-gate.ps1` directly.
- VROOM unavailable: final certification records VROOM as `EVIDENCE_GAP`; do not claim VROOM completion without evidence.
