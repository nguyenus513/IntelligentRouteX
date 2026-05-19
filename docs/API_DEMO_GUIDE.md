# API Demo Guide

## Dynamic ML Dispatch Backend

Use `X-Api-Key: demo-key` and `X-Tenant-Id: demo` for local demo calls.

Endpoints:

- `POST /api/v1/live/jobs`: create a dynamic live job.
- `POST /api/v1/live/jobs/{jobId}/orders`: inject live orders.
- `POST /api/v1/live/jobs/{jobId}/drivers/{driverId}/telemetry`: update driver telemetry.
- `POST /api/v1/live/jobs/{jobId}/cycle`: run a dynamic ML dispatch cycle.
- `GET /api/v1/live/jobs/{jobId}/state`: read live state.
- `GET /api/v1/live/jobs/{jobId}/events`: read server-sent events.
- `POST /api/v1/live/jobs/{jobId}/rescue`: trigger rescue repair.

The dynamic cycle response reports `forecastUsed`, `greedRlAction`, `triModelRepairUsed`, routes, and safety diagnostics.

Certification gate: `scripts/run-v0.9.11-dynamic-ml-dispatch-gate.ps1`.

