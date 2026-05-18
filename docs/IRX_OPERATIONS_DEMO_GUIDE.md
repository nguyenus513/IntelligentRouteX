# IRX Operations Demo Guide

## Start

```powershell
.\scripts\irx.ps1 up -Profile local
```

Starts backend on `18116`, dashboard on `5173`, waits for `/api/v1/health`, waits for `/playground`, then opens Playground.

## Check

```powershell
.\scripts\irx.ps1 status
```

Reports backend/dashboard health, PIDs, runtime queue, workers, artifacts.

## Test

```powershell
.\scripts\irx.ps1 test -Quick
```

Runs compile, dashboard typecheck/build, API contract gate, Playground gate, BigData-lite gate, and writes `artifacts/test-reports/v0.9.9.6-one-click-start/one-click-system-summary.json`.

## Stop

```powershell
.\scripts\irx.ps1 down
```

Stops PID-tracked backend/dashboard and clears stale ports.

## Package

```powershell
.\scripts\irx.ps1 package
```

Builds backend jar, dashboard dist, docs, scripts, sample reports, and `release/irx-v1.0.zip`.
