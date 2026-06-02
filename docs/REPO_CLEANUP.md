# Repository Cleanup Record

This repo intentionally keeps the Java backend, React dashboard, benchmark tooling, and packaging scripts. Generated artifacts and local runtime binaries stay out of git.

## Kept Intentionally

- `src/main/java` and `src/main/resources`: Spring Boot API, dispatch core, live controllers, solver integration, and runtime config.
- `src/test/java`: backend tests and performance/test fixtures.
- `playground/src`: React/Vite control-tower dashboard, live map, benchmark, demo, trace, and API sandbox UI.
- `scripts`: benchmark, smoke, packaging, OSRM, and release helper scripts.
- `docs`: architecture, API, benchmark, dashboard, packaging, and report documentation.
- `benchmarks`: lightweight benchmark metadata and official/reference dataset manifests where tracked.

## Removed Or Excluded

- Local build output: `build/`, `.gradle/`, `out/`, `playground/dist/`.
- Local dependency caches: `node_modules/`, `.venv/`, `.pytest_cache/`, `__pycache__/`.
- Generated reports: `artifacts/test-reports/`, generated charts, screenshots, logs, and temporary smoke output.
- Heavy runtime assets: portable JRE, portable Python, VROOM binary, OSRM binary, `.osrm` map data, release zip/exe.
- Secret/config files: `.env`, `.env.*`, local API keys, tunnel keys, and machine-specific paths.

## Current Known Loose Ends

- `playground/tests/` was an untracked local Playwright scratch test using older button labels; it should be removed unless converted into a maintained test suite.
- Windows portable release is source-ready, but the real artifact cannot be built until native runtimes are supplied.
- README and docs must stay aligned with the actual dashboard/API shape whenever tabs or endpoint names change.

## Cleanup Rule

Before pushing:

```powershell
git status --short
.\gradlew.bat compileJava -x test --no-daemon --console=plain
cd playground
npm run typecheck
npm run build
```

Only commit source, docs, configs, and scripts. Do not commit generated runtime outputs or heavy native binaries.
