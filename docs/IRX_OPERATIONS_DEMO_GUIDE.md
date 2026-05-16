# IRX Operations Demo Guide

## Start Backend

```powershell
$env:GRADLE_USER_HOME=(Resolve-Path '.').Path + '\.gradle-tmp'
.\gradlew.bat bootRun --no-daemon --args='--spring.profiles.active=dispatch-v2-dashboard-demo --server.port=18116'
```

## Dashboard

```powershell
cd dashboard
npm run dev
```

## Gates

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts/run-fast-gate.ps1 -BaseUrl http://localhost:18116
powershell.exe -ExecutionPolicy Bypass -File scripts/run-quality-benchmark-gate.ps1 -BaseUrl http://localhost:18116
powershell.exe -ExecutionPolicy Bypass -File scripts/run-live-stress-gate.ps1 -BaseUrl http://localhost:18116
powershell.exe -ExecutionPolicy Bypass -File scripts/run-rescue-gate.ps1 -BaseUrl http://localhost:18116
powershell.exe -ExecutionPolicy Bypass -File scripts/run-final-system-gate.ps1 -BaseUrl http://localhost:18116
```

## External Solver Environment

```powershell
$env:VROOM_BASE_URL='http://localhost:3000'
# or
$env:VROOM_BIN='C:\path\to\vroom.exe'
```

PyVRP is detected through Python:

```powershell
py -3 -c "import pyvrp; print(getattr(pyvrp, '__version__', 'unknown'))"
```

## Reading Victory Report

- Benchmark profile shows FAST/QUALITY mode and routing semantics.
- Objective summary shows raw-vs-objective tradeoff.
- Why Selected explains best distance seed, best objective seed, and dominance reason.
- Move trace summary shows accepted/rejected improvement activity.
- External contributor status shows PyVRP/VROOM `OK`, `TIMEOUT`, `ERROR`, or `EVIDENCE_GAP`.
