# IRX Reproducibility Guide

## Backend

```powershell
$env:GRADLE_USER_HOME=(Resolve-Path '.').Path + '\.gradle-tmp'
.\gradlew.bat bootRun --no-daemon --args='--spring.profiles.active=dispatch-v2-dashboard-demo --server.port=18116'
```

## Build Gates

```powershell
$env:GRADLE_USER_HOME=(Resolve-Path '.').Path + '\.gradle-tmp'
.\gradlew.bat compileJava --no-daemon --console=plain
cd dashboard
npm run typecheck
npm run build
cd ..
```

## Certification Gates

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts/run-fast-gate.ps1 -BaseUrl http://localhost:18116 -DatasetTimeoutSeconds 260
powershell.exe -ExecutionPolicy Bypass -File scripts/run-quality-benchmark-gate.ps1 -BaseUrl http://localhost:18116 -DatasetTimeoutSeconds 520
powershell.exe -ExecutionPolicy Bypass -File scripts/run-academic-static-gate.ps1 -BaseUrl http://localhost:18116
powershell.exe -ExecutionPolicy Bypass -File scripts/run-pdptw-gate.ps1 -BaseUrl http://localhost:18116
powershell.exe -ExecutionPolicy Bypass -File scripts/run-external-solver-gate.ps1 -BaseUrl http://localhost:18116
powershell.exe -ExecutionPolicy Bypass -File scripts/run-live-stress-gate.ps1 -BaseUrl http://localhost:18116
powershell.exe -ExecutionPolicy Bypass -File scripts/run-rescue-gate.ps1 -BaseUrl http://localhost:18116
```

## Full Loop

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts/run-final-certification-loop.ps1 -BaseUrl http://localhost:18116
```

If a subgroup fails, fix only that subgroup and rerun the subgroup gate before rerunning the full loop.

## External Solvers

PyVRP check:

```powershell
py -3 -c "import pyvrp; print(getattr(pyvrp, '__version__', 'unknown'))"
```

VROOM options:

```powershell
$env:VROOM_BASE_URL='http://localhost:3000'
# or
$env:VROOM_BIN='C:\path\to\vroom.exe'
```

If VROOM is not configured, expected status is `EVIDENCE_GAP`.

