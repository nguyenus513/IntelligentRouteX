# BigData-lite API

BigData-lite is IRX's lightweight runtime pattern for larger API inputs. It is designed for local production-demo and pilot-style workloads without claiming Kafka, Spark, or distributed stream processing.

## Flow

```text
POST batch -> validate -> normalize -> queue admission -> worker lifecycle
-> result summary -> paginated item access -> artifacts/events/metrics
-> retry/dead-letter/requeue for failures
```

## Batch ingest

Endpoint: `POST /api/v1/bigdata/batches`.

Request fields:

- `batchId`: caller batch identifier.
- `tenantId`: logical tenant.
- `items`: array of order-like records.
- `options.validationMode`: `STRICT` for validation reporting.
- `options.dedupeKey`: field used to identify duplicates.

Gate evidence covers `100` and `1000` item batches in `v0.9.9.3-bigdata-lite-api`.

## Validation and normalization

Invalid rows are accounted for in rejected/dead-letter counts. The API does not silently ignore invalid input.

## Queue and backpressure

BigData-lite uses queue admission and a backpressure response for overloaded input. Gate evidence checks a backpressure response and confirms the system does not crash under burst-style input.

Current runtime hardening adds an async worker queue so batch ingest no longer runs dispatch work on the request thread. Accepted batches return `202 Accepted`, enter a priority lane, and are processed by background workers. Runtime limits are configurable:

- `IRX_BIGDATA_MAX_BATCH_ITEMS`
- `IRX_BIGDATA_MAX_QUEUE_DEPTH`
- `IRX_BIGDATA_MAX_LANE_DEPTH`
- `IRX_BIGDATA_WORKER_COUNT`
- `IRX_BIGDATA_CHUNK_SIZE`

Priority lanes protect urgent traffic from heavy batch input:

1. `RESCUE_QUEUE`
2. `LIVE_QUEUE`
3. `STATIC_QUEUE`
4. `DIAGNOSTIC_QUEUE`
5. `EXPORT_QUEUE`
6. `DEAD_LETTER_QUEUE`

Large batches are split into chunks before execution, so rescue/live telemetry work can be scheduled between chunks instead of waiting for a whole large batch to finish. Duplicate rows can be rejected with `options.dedupeKey`. If total or lane depth is exhausted, the API returns `503` with `Retry-After` and increments `backpressureRejected` metrics.

## Optional Kafka mode

Kafka is optional, not required for local BigData-lite. The repo already contains Kafka streaming components for dispatch requests/results/DLQ and a Docker Compose profile for a local broker:

```powershell
docker compose --profile optional-kafka up kafka
```

Enable dispatch streaming with:

```powershell
$env:IRX_STREAMING_ENABLED="true"
$env:IRX_BIGDATA_KAFKA_ENABLED="true"
$env:IRX_KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
```

Default topics:

- `irx.bigdata.chunks.v1`
- `irx.bigdata.results.v1`
- `irx.dispatch.requests.v1`
- `irx.dispatch.results.v1`
- `irx.dispatch.dlq.v1`

When `IRX_BIGDATA_KAFKA_ENABLED=true`, BigData-lite publishes batch chunks to Kafka and the worker consumes them from `irx.bigdata.chunks.v1`. Completed batch summaries are published to `irx.bigdata.results.v1`. If publish fails and `IRX_BIGDATA_KAFKA_FALLBACK_TO_LOCAL=true`, chunks fall back to the local in-memory lane queue. Kafka should be presented as the production extension path for distributed ingestion. BigData-lite remains the default local/demo path.

## Optional Postgres state store

Postgres can persist job metadata, event timeline, DLQ markers, and result summaries:

```powershell
docker compose --profile optional-persistent up postgres
$env:IRX_BIGDATA_POSTGRES_ENABLED="true"
$env:IRX_BIGDATA_POSTGRES_URL="jdbc:postgresql://localhost:5432/irx"
$env:IRX_BIGDATA_POSTGRES_USER="irx"
$env:IRX_BIGDATA_POSTGRES_PASSWORD="irx"
```

Tables are created automatically when the Postgres store is enabled:

- `bigdata_lite_jobs`
- `bigdata_lite_events`
- `bigdata_lite_dead_letter`
- `bigdata_lite_results`

Use Postgres for durable state and audit. Use Kafka for high-throughput transport. Keep in-memory mode for lightweight local demos.

## One-command local run

Start Docker Desktop first, then run:

```powershell
.\scripts\start-bigdata-kafka-postgres.ps1
```

In another terminal, verify:

```powershell
.\scripts\test-bigdata-kafka-postgres.ps1
```

If Docker is not running, the start script exits early with a clear Docker daemon error. Start Docker Desktop and rerun it.

## Pagination

Large outputs are returned through page/cursor endpoints instead of one large response:

- `GET /bigdata/batches/{batchId}/items?page=0&size=50`
- `GET /jobs/{jobId}/routes?limit=100&cursor=...`
- `GET /jobs/{jobId}/assignments?limit=500&cursor=...`
- `GET /jobs/{jobId}/events?limit=200&cursor=...`

## Dead-letter and requeue

Dead-letter support keeps failed items/jobs visible for analysis and requeue:

- `GET /bigdata/dead-letter`
- `POST /bigdata/dead-letter/{itemId}/requeue`
- `GET /runtime/dead-letter`
- `POST /runtime/dead-letter/{jobId}/requeue`

## Artifacts and metrics

BigData-lite writes/list exposes artifacts, event logs, and runtime metrics. Evidence paths:

- `artifacts/test-reports/v0.9.9.3-bigdata-lite-api/final-bigdata-lite-api-summary.json`
- `artifacts/test-reports/v0.9.9.6-one-click-start/bigdata-lite/final-bigdata-lite-api-summary.json`

## Limitations

The current implementation is BigData-lite: in-memory/file-style runtime behavior for local demo. It is intentionally not a distributed queue or data lake implementation.
