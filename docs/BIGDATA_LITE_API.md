# BigData-lite API

BigData-lite provides large input handling without Kafka/Spark:

`Ingest -> Normalize -> Queue -> Worker -> Store -> Paginate/Stream/Artifact`.

Contract guarantees:
- Async batch admission with idempotency support.
- Strict invalid-row accounting.
- Backpressure rejection with stable error envelope.
- Cursor/page output for large assignment/route/event sets.
- Retry/dead-letter and requeue endpoints.
- Runtime metrics for queue depth, events, artifacts, and worker state.
