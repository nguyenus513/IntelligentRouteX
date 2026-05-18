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
