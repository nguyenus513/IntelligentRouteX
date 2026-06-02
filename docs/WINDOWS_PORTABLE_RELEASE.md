# IRX Windows Portable Release

This release mode packages IRX for Windows x64 without requiring Java, Node, Python, Docker, or system solver installs on the target machine.

## Required runtime inputs

The packager intentionally fails if a required runtime is missing. Provide these paths as environment variables or parameters:

- `IRX_PORTABLE_JRE_DIR`: JRE 21 Windows x64 root containing `bin/java.exe`.
- `IRX_PORTABLE_PYTHON_DIR`: portable Python root containing `python.exe` and installed `pyvrp`.
- `IRX_PORTABLE_VROOM_EXE`: native Windows `vroom.exe`.
- `IRX_PORTABLE_OSRM_DIR`: OSRM Windows binary directory containing `osrm-routed.exe`.
- `IRX_PORTABLE_OSRM_DATA_DIR`: prebuilt HCMC OSRM data containing at least one `.osrm` file.

## Target package architecture

The portable package is a self-contained folder. The target PC only runs `start-irx.bat`; it must not need system Java, Node, Python, Docker, VROOM, OSRM, PyVRP, or OR-Tools installs.

```text
irx-portable-windows-x64/
  start-irx.bat
  stop-irx.bat
  app/
    irx-backend.jar
    public/                  # built React dashboard
    config/application-portable.yml
  runtime/
    jre/bin/java.exe
    python/python.exe        # pyvrp installed here
    vroom/vroom.exe
    osrm/osrm-routed.exe
  data/
    osrm/*.osrm              # prebuilt map graph
    logs/
```

Runtime rule:

```text
FE route drawing = frontend fetches route geometry from OSRM.
Backend optimization = backend uses solver outputs + OSRM distance/time, then returns final stop order + trace.
Portable launcher = starts OSRM first, then backend, then serves FE from backend static resources.
```

## Detailed implementation plan

### Phase 1 — Freeze portable contract

- Keep package gates strict: missing JRE/Python/PyVRP/VROOM/OSRM/map must fail release build.
- Do not commit `runtime/`, `.osrm`, `.zip`, or `.exe` artifacts to git.
- Publish final heavy artifacts through GitHub Releases or local handoff drive.
- Keep repo source runnable without portable assets.
- Keep generated logs under package `data/logs/`.

### Phase 2 — Runtime collection

- JRE: use Temurin/OpenJDK 21 Windows x64 JRE/JDK folder; verify `bin/java.exe`.
- Python: use embeddable/portable Python x64 or copied venv-like runtime; verify `python.exe -c "import pyvrp"`.
- OR-Tools: keep Java dependency inside backend build; no separate target install required if backend jar contains dependency.
- VROOM: provide native Windows `vroom.exe`; verify it starts and returns version/help.
- OSRM: provide `osrm-routed.exe` plus required DLLs; verify `osrm-routed --version`.
- OSRM data: prebuild `.osrm` graph for demo area; target launcher must not run extract/contract on user machine.

### Phase 3 — Package build gate

- Run current repo baseline smoke before packaging.
- Build backend jar with `gradlew.bat bootJar`.
- Build dashboard with `npm run build` in `playground/`.
- Copy FE build into `app/public/`.
- Copy all runtimes into `runtime/`.
- Generate `application-portable.yml` and launcher scripts.
- Zip folder as `irx-portable-windows-x64.zip`.

### Phase 4 — Portable startup gate

- `start-irx.bat` starts OSRM on `127.0.0.1:5001`.
- Launcher waits until OSRM route probe succeeds.
- Launcher starts backend on configured port.
- Launcher waits until backend `/v1/health` succeeds.
- Browser can open dashboard without Node/Vite.
- `stop-irx.bat` stops backend and OSRM started by the package.

### Phase 5 — Functional smoke gate

- Health: backend responds and reports ready.
- OSRM: route probe returns valid geometry/distance/duration.
- PyVRP: bundled Python imports `pyvrp`.
- VROOM: backend can call bundled VROOM path.
- OR-Tools: backend compare includes OR-Tools row.
- Live: start live, add drivers, add orders, dispatch cycle returns assignments.
- Route: final route starts from driver location, includes pickup/dropoff precedence, and keeps route geometry.
- Driver simulation: driver moves, consumed route segment disappears, pickup pin disappears after pickup, dropoff pin disappears after delivery.
- Benchmark: IRX/VROOM/OR-Tools/PyVRP/Nearest/One-by-one all return rows on the same dataset.
- BigData lite: ingest + runtime summary works without UI freeze.

### Phase 6 — Baseline comparison gate

- Run same benchmark dataset on source repo and portable package.
- Compare solver rows: `IRX`, `VROOM`, `ORTOOLS`, `PYVRP`, `NEAREST`, `ONE_BY_ONE`.
- Compare metrics: runtime, OSRM distance, late count, coverage, final P/D sequence.
- Accept portable if output is functionally equivalent or better than baseline.
- Fail if any solver silently disappears, coverage drops unexpectedly, or backend returns straight-line-only distance.

### Phase 7 — Fresh-machine test gate

- Test on Windows machine without Java in `PATH`.
- Test on Windows machine without Node/npm in `PATH`.
- Test on Windows machine without Python in `PATH`.
- Test with no Docker Desktop installed/running.
- Launch from path with spaces, e.g. `D:\IRX Demo\irx-portable-windows-x64`.
- Launch offline after package is copied locally.

### Phase 8 — Release gate

- Produce `irx-portable-windows-x64.zip`.
- Optional: produce `IRX-ControlTower-Setup.exe` using Inno Setup.
- Attach smoke report and baseline compare report.
- Tag release with exact commit SHA.
- Include runtime provenance note: JRE/Python/VROOM/OSRM versions and map build date.

## Detailed test plan

### A. Source baseline

```powershell
.\scripts\smoke-package-baseline.ps1
```

Pass criteria:

- Java compile passes.
- Frontend typecheck/build passes.
- Baseline summary exists at `artifacts/test-reports/package-baseline/current-summary.json`.
- No generated release artifact is committed.

### B. Runtime presence

```powershell
Test-Path C:\runtimes\jre-21\bin\java.exe
Test-Path C:\runtimes\python-pyvrp\python.exe
C:\runtimes\python-pyvrp\python.exe -c "import pyvrp; print(pyvrp.__version__)"
Test-Path C:\runtimes\vroom\vroom.exe
Test-Path C:\runtimes\osrm\osrm-routed.exe
Get-ChildItem C:\runtimes\osrm-hcmc -Filter *.osrm
```

Pass criteria:

- All commands succeed.
- PyVRP import works using portable Python, not system Python.
- OSRM data folder has at least one `.osrm` base file.

### C. Package build

```powershell
.\scripts\package-windows-portable.ps1 `
  -JreDir C:\runtimes\jre-21 `
  -PythonDir C:\runtimes\python-pyvrp `
  -VroomExe C:\runtimes\vroom\vroom.exe `
  -OsrmDir C:\runtimes\osrm `
  -OsrmDataDir C:\runtimes\osrm-hcmc
```

Pass criteria:

- Build fails fast if any runtime is missing.
- On success, bundle folder and zip exist.
- Bundle contains only generated app/runtime/data, no accidental source tree copy.

### D. Portable smoke

```powershell
build\release\windows-portable\irx-portable-windows-x64\start-irx.bat
.\scripts\smoke-windows-portable.ps1 -BundleRoot build\release\windows-portable\irx-portable-windows-x64
```

Pass criteria:

- OSRM probe returns `Ok`.
- Backend health succeeds.
- FE HTTP succeeds.
- Compare job succeeds.
- BigData ingest/runtime succeeds.
- Smoke summary exists in package logs.

### E. Baseline vs portable compare

```powershell
.\scripts\compare-package-baseline.ps1
```

Pass criteria:

- Report exists at `artifacts/test-reports/package-compare/report.md`.
- Portable includes same solver families as baseline.
- IRX final keeps 100% coverage on demo datasets.
- Distance and final P/D sequence are explained in trace.

### F. Live demo regression

Manual flow:

```text
1. Open dashboard from portable backend.
2. Press Start Live.
3. Keep Auto Order OFF and Auto Driver OFF by default.
4. Pin 3-4 drivers manually.
5. Pin 6-10 orders manually.
6. Confirm orders enter backend buffer.
7. Confirm backend returns final driver assignment + P/D sequence.
8. Confirm route starts at moving driver position.
9. Confirm driver moves along route.
10. Confirm pickup pin disappears only after pickup.
11. Confirm dropoff pin disappears only after delivery.
12. Confirm consumed route segments disappear behind driver.
13. Press Cancel & Clear Map.
14. Confirm queues/tasks/routes/pins clear.
```

Pass criteria:

- FE does not self-solve final assignment when backend is available.
- Driver marker does not leave stale start pins.
- Route does not continuously rewrite while driver is following frozen segment.
- Console/log panel does not auto-scroll unless user enables it.

### G. Fixed scenario demo

Manual flow:

```text
1. Press Start Demo.
2. Scenario creates 15 drivers and 40 orders.
3. Backend receives all scenario events.
4. Dispatch runs with seed race + IRX refinement.
5. Drivers move like live mode.
6. Pickups/dropoffs disappear only when completed.
```

Pass criteria:

- Scenario is deterministic enough for presentation.
- Orders/drivers are spatially diverse.
- UI remains responsive.
- Route colors remain distinguishable.

### H. Benchmark regression

Run benchmark from UI or API on all packaged datasets.

Pass criteria:

- Single Start Benchmark button toggles to Stop Benchmark.
- Table has one `IRX` row only, not duplicate native/final rows.
- Baselines include `VROOM`, `ORTOOLS`, `PYVRP`, `NEAREST`, `ONE_BY_ONE`.
- Sequence column shows compact P/D order, e.g. `P1-P2-D2-D1`.
- Distance uses OSRM, not straight-line fallback, unless fallback is explicitly labeled.

### I. Fresh machine acceptance

On a clean Windows VM:

```text
1. Copy zip.
2. Extract.
3. Run start-irx.bat.
4. Open dashboard.
5. Run portable smoke.
6. Run fixed scenario demo.
7. Stop app.
```

Pass criteria:

- No Java/Node/Python/Docker install prompt.
- No admin rights required.
- Works from a folder path containing spaces.
- Logs are written inside package `data/logs/`.

## Known blockers before real artifact

- Current machine has Java, but not a portable JRE folder prepared at `C:\runtimes\jre-21`.
- Current machine Python does not have PyVRP installed for portable use.
- `vroom.exe` is not currently available in `PATH`.
- `osrm-routed.exe` and prebuilt `.osrm` data are not currently available in `PATH`.
- Therefore the strict packager correctly fails until native solver runtimes are supplied.

## Build portable zip

Recommended full release gate:

One-command build on the packaging machine:

```powershell
.\scripts\build-windows-portable-all.ps1 -RuntimeRoot C:\runtimes -SkipInstaller
```

This prepares runtimes under `C:\runtimes`, then runs the release gate.

If runtimes already exist, use the gate directly:

```powershell
.\scripts\run-windows-portable-release-gate.ps1 `
  -JreDir C:\runtimes\jre-21 `
  -PythonDir C:\runtimes\python-pyvrp `
  -VroomExe C:\runtimes\vroom\vroom.exe `
  -OsrmDir C:\runtimes\osrm `
  -OsrmDataDir C:\runtimes\osrm-hcmc
```

This runs source compile, frontend checks, source baseline smoke, runtime preflight, portable packaging, portable smoke, baseline-vs-portable comparison, and installer build when available.

Prepare runtimes only:

```powershell
.\scripts\prepare-windows-portable-runtimes.ps1 -RuntimeRoot C:\runtimes
```

Runtime preparation creates:

- `C:\runtimes\jre-21`
- `C:\runtimes\python-pyvrp`
- `C:\runtimes\vroom\vroom.exe`
- `C:\runtimes\osrm\osrm-routed.exe`
- `C:\runtimes\osrm-hcmc\*.osrm`

Note: VROOM does not always publish a Windows binary in upstream GitHub releases. If the script reports no official `vroom.exe`, build/provide `vroom.exe` manually at `C:\runtimes\vroom\vroom.exe`, then rerun the release gate.

Runtime-only preflight:

```powershell
.\scripts\check-windows-portable-runtimes.ps1 `
  -JreDir C:\runtimes\jre-21 `
  -PythonDir C:\runtimes\python-pyvrp `
  -VroomExe C:\runtimes\vroom\vroom.exe `
  -OsrmDir C:\runtimes\osrm `
  -OsrmDataDir C:\runtimes\osrm-hcmc
```

Manual package command:

```powershell
.\scripts\package-windows-portable.ps1 `
  -JreDir C:\runtimes\jre-21 `
  -PythonDir C:\runtimes\python-pyvrp `
  -VroomExe C:\runtimes\vroom\vroom.exe `
  -OsrmDir C:\runtimes\osrm `
  -OsrmDataDir C:\runtimes\osrm-hcmc
```

Output:

- `build/release/windows-portable/irx-portable-windows-x64/`
- `build/release/irx-portable-windows-x64.zip`

## Build installer EXE

```powershell
.\scripts\package-windows-installer.ps1
```

Preferred output with Inno Setup:

- `build/release/IRX-ControlTower-Setup.exe`

If Inno Setup is unavailable, install it or ship the portable zip.

## Run smoke test

Start the portable bundle first:

```powershell
build\release\windows-portable\irx-portable-windows-x64\start-irx.bat
```

Then run:

```powershell
.\scripts\smoke-windows-portable.ps1 -BundleRoot build\release\windows-portable\irx-portable-windows-x64
```

The gate checks:

- Java runtime bundled.
- Python + PyVRP import works.
- VROOM binary exists.
- OSRM binary and map exist.
- OSRM route probe returns `Ok`.
- Backend `/v1/health` responds.
- Frontend responds.
- Compare job runs.
- BigData ingest/runtime works.

## Compare against current repo build

```powershell
.\scripts\smoke-package-baseline.ps1
.\scripts\compare-package-baseline.ps1
```

Reports:

- `artifacts/test-reports/package-baseline/current-summary.json`
- `build/release/windows-portable/irx-portable-windows-x64/data/logs/smoke/smoke-summary.json`
- `artifacts/test-reports/package-compare/report.md`

## Notes

- This package does not use Docker on the target machine.
- OSRM data is prebuilt; the app does not download Overpass data at runtime.
- Release artifacts can be large and should be published via GitHub Releases, not committed to git.

