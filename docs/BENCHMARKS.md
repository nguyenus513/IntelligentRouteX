# Benchmarks

This repo keeps backend benchmark scripts and API-driven certification gates.

Dashboard/UI benchmark evidence has been removed as part of repo cleanup.
Current benchmark use is backend-only: scripts call API endpoints and write local reports when run.
Generated reports are not kept in git after cleanup.

Run relevant gates directly from `scripts/` against a running backend.

## v1.0.0 Production API Core Gates

Certification entrypoint:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-production-api-core-gate.ps1 -BaseUrl http://localhost:18116 -OutputDir artifacts/test-reports/v1.0.0-production-api-core/final
```

The gate verifies compile, OpenAPI/AsyncAPI contracts, runtime store abstractions, queue/worker abstractions, static/live/rescue/compare APIs, execution timeline, security/idempotency/rate-limit hooks, artifact store, event stream, observability, and Docker Compose presence.

## v1.0.1 Backend Core Recertification

After removing dashboard/mobile/demo surfaces, backend-only core was recertified with:
- clean backend-only dependency check
- compileJava
- production API core gate
- static dispatch smoke
- live dynamic smoke
- compare API smoke
- execution timeline/events smoke
- Adaptive ML QUALITY_SEEKING diagnostics check
- security, idempotency, rate-limit, event stream, observability checks

Final artifact: `artifacts/test-reports/v1.0.1-backend-core-recertified/final-summary.json`.
