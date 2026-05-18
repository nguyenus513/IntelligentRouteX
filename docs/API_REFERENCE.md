# API Reference

Base URL: `http://localhost:18116/api/v1`.

## Success envelope

```json
{
  "ok": true,
  "requestId": "REQ-123",
  "data": {},
  "meta": { "version": "v1", "timestamp": "2026-05-18T00:00:00Z" }
}
```

## Error envelope

```json
{
  "ok": false,
  "requestId": "REQ-123",
  "error": { "code": "VALIDATION_ERROR", "message": "Invalid request payload", "details": [] },
  "meta": { "version": "v1", "timestamp": "2026-05-18T00:00:00Z" }
}
```

Stable error codes used by the contract: `VALIDATION_ERROR`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `UNAUTHORIZED`, `FORBIDDEN`, `JOB_CANCELLED`, `JOB_TIMEOUT`, `ARTIFACT_ACCESS_DENIED`, `BACKPRESSURE_REJECTED`, `INTERNAL_ERROR`.

## Idempotency

Creation endpoints accept `Idempotency-Key`. Same key and same payload returns the original resource. Same key and a different payload returns `CONFLICT`.

## Job lifecycle

Endpoints:

- `POST /jobs`
- `GET /jobs/{jobId}`
- `GET /jobs/{jobId}/result`
- `POST /jobs/{jobId}/cancel`
- `GET /jobs/{jobId}/events`
- `GET /jobs/{jobId}/artifacts`

Statuses: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMEOUT`.

## Static dispatch API

- `POST /static/dispatch`
- `POST /static/dispatch/jobs`
- `GET /static/dispatch/jobs/{jobId}`
- `GET /static/dispatch/jobs/{jobId}/result`

Static result includes `finalSolver`, `coverage`, `metrics`, `routes`, and `diagnostics` with Adaptive ML and dominance guard data.

## Live rolling API

- `POST /live/start`
- `POST /live/stop`
- `GET /live/state`
- `POST /live/orders`
- `POST /live/drivers/location`
- `POST /live/cycles/run-now`
- `GET /live/cycles/{cycleId}`
- `GET /live/cycles/{cycleId}/result`
- `GET /live/events`

## Rescue API

- `POST /rescue/jobs`
- `GET /rescue/jobs/{jobId}`
- `GET /rescue/jobs/{jobId}/result`

Rescue result contains `beforeLate`, `afterLate`, `lateNotWorse`, `rescuedRouteCount`, and `rescueDominanceGuard`.

## BigData-lite API

- `POST /bigdata/batches`
- `GET /bigdata/batches/{batchId}`
- `GET /bigdata/batches/{batchId}/items?page=0&size=50`
- `POST /bigdata/batches/{batchId}/requeue`
- `GET /bigdata/dead-letter`
- `POST /bigdata/dead-letter/{itemId}/requeue`
- `GET /bigdata/metrics`

## Artifact API

- `GET /artifacts`
- `GET /artifacts/{artifactId}`
- `GET /artifacts/{artifactId}/download`
- `DELETE /artifacts/{artifactId}`

Path traversal and invalid artifact identifiers are blocked.

## Event API

- `GET /events`
- `GET /jobs/{jobId}/events`
- `GET /live/events`

Event records include `eventId`, `type`, `jobId`, `timestamp`, and `data`.

## Runtime and metrics API

- `GET /health`
- `GET /runtime/state`
- `GET /runtime/queues`
- `GET /runtime/workers`
- `GET /metrics`

Metrics include job counts, queue depths, artifact count, event count, and live telemetry count where available.
