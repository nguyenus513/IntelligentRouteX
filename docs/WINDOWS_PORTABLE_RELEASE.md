# IRX Windows Portable Release

This release mode packages IRX for Windows x64 without requiring Java, Node, Python, Docker, or system solver installs on the target machine.

## Required runtime inputs

The packager intentionally fails if a required runtime is missing. Provide these paths as environment variables or parameters:

- `IRX_PORTABLE_JRE_DIR`: JRE 21 Windows x64 root containing `bin/java.exe`.
- `IRX_PORTABLE_PYTHON_DIR`: portable Python root containing `python.exe` and installed `pyvrp`.
- `IRX_PORTABLE_VROOM_EXE`: native Windows `vroom.exe`.
- `IRX_PORTABLE_OSRM_DIR`: OSRM Windows binary directory containing `osrm-routed.exe`.
- `IRX_PORTABLE_OSRM_DATA_DIR`: prebuilt HCMC OSRM data containing at least one `.osrm` file.

## Build portable zip

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

