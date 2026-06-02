# IntelligentRouteX

IRX is a Java/Spring Boot dispatch optimization platform with a React control-tower dashboard for live routing, solver comparison, benchmark replay, and demo presentation.

## What This Repo Contains

- Spring Boot backend API for dispatch jobs, live sessions, rescue, compare, and BigData-lite ingestion.
- Hybrid optimization flow: seed race from IRX/VROOM/OR-Tools/PyVRP, IRX refinement, dominance guard, and final route trace.
- React/Vite dashboard in `playground/` for live map, benchmark, demo scenario, decision trace, and API sandbox.
- Packaging scripts for Windows portable release and installer-style delivery.
- Documentation for APIs, architecture, dynamic dispatch, benchmark evidence, dashboard usage, and report writing.

## Quick Start

Install Python solver/ML runtime dependencies:

```powershell
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\check-ml-runtime.ps1
```

Compile backend:

```powershell
.\gradlew.bat compileJava -x test --no-daemon --console=plain
```

Run backend API locally:

```powershell
.\gradlew.bat bootRun --args="--server.port=18116"
```

Run dashboard locally:

```powershell
cd playground
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Validation

Backend compile:

```powershell
.\gradlew.bat compileJava -x test --no-daemon --console=plain
```

Frontend checks:

```powershell
cd playground
npm run typecheck
npm run build
```

Portable baseline smoke:

```powershell
.\scripts\smoke-package-baseline.ps1
```

Full Windows portable release gate:

```powershell
.\scripts\build-windows-portable-all.ps1 -RuntimeRoot C:\runtimes -SkipInstaller
```

If runtimes are already prepared:

```powershell
.\scripts\run-windows-portable-release-gate.ps1 `
  -JreDir C:\runtimes\jre-21 `
  -PythonDir C:\runtimes\python-pyvrp `
  -VroomExe C:\runtimes\vroom\vroom.exe `
  -OsrmDir C:\runtimes\osrm `
  -OsrmDataDir C:\runtimes\osrm-hcmc
```

## Main Docs

- `docs/DASHBOARD_TUTORIAL.md` — full dashboard usage guide.
- `docs/REPORT_GUIDE.md` — report structure, best results, screenshots, and demo evidence to include.
- `docs/API_REFERENCE.md` — API overview.
- `docs/API_EXAMPLES.md` — API examples.
- `docs/DYNAMIC_DISPATCH.md` — live/stateful dispatch concept.
- `docs/ADAPTIVE_ML_POLICY.md` — adaptive optimization policy.
- `docs/BENCHMARKS.md` — benchmark and solver comparison evidence.
- `docs/WINDOWS_PORTABLE_RELEASE.md` — Windows portable packaging and smoke plan.
- `docs/REPO_CLEANUP.md` — cleanup rules and generated-file policy.

## Packaging Status

The repo can build backend and dashboard from source. A fully portable Windows package additionally needs native runtime inputs:

- JRE 21 Windows x64.
- Portable Python with `pyvrp` installed.
- Native `vroom.exe`.
- Native OSRM binaries plus prebuilt `.osrm` map data.

These heavy runtime files must not be committed to git. Use `docs/WINDOWS_PORTABLE_RELEASE.md` for the release flow.
