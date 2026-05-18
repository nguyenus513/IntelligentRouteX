# Architecture

## High-level view

```text
Browser Playground
  -> React API adapter
  -> /api/v1 contract facade
  -> runtime job/session stores
  -> queue lanes and worker facade
  -> optimizer core + Adaptive ML policy
  -> results, artifacts, events, metrics
```

## API facade

The API facade exposes a stable `/api/v1` contract:

- Response envelope: `{ ok, requestId, data, meta }`
- Error envelope: `{ ok:false, requestId, error, meta }`
- Job lifecycle: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMEOUT`
- Endpoint groups: jobs, static, live, rescue, BigData-lite, artifacts, events, runtime metrics.

## Runtime queue/store

The production-runtime MVP uses abstractions for dispatch jobs, live sessions, results, artifacts, idempotency, and rate state. The current implementation is in-memory/file-system oriented for local demo use. Queue lanes include `FAST`, `QUALITY`, `LIVE`, `RESCUE`, and `BENCHMARK` in v0.9.9.2, with BigData-lite facade lanes including static/live/rescue/diagnostic/dead-letter concepts.

## Optimizer core

The core dispatch layer keeps evaluator and dominance guards as final safety authority. Adaptive policy can rank and budget candidate search, but accepted results remain guarded against coverage, late, and dominance regressions.

## Seed contributors

IRX can use internal heuristics and external solver seed evidence. PyVRP evidence is committed as completed in final certification. VROOM is documented as an evidence gap where local worker/native completion is unavailable.

## Adaptive ML

Adaptive ML has four conceptual parts:

- `AdaptiveSeedPolicy`: seed-source preference.
- `AdaptiveOperatorPolicy`: operator budgeting.
- `AdaptiveMovePriority`: move scoring and ordering.
- `AdaptiveRewardCalculator`: reward updates from accepted/rejected outcomes.

## BigData-lite flow

```text
Batch request -> validation/normalization -> queue admission/backpressure
-> worker lifecycle -> result summary -> paginated rows -> artifacts/events/metrics
-> retry/dead-letter/requeue when needed
```

## Playground flow

The Playground is a client of the locked API contract. It calls static, live, rescue, and BigData-lite endpoints, then renders result summary, assignments, Adaptive ML diagnostics, baseline comparison, events, artifacts, and raw JSON.

## Deployment/package

`./scripts/irx.ps1 package` builds a backend jar, dashboard `dist`, scripts, docs, Docker files, and sample reports into `release/irx-v1.0`, then creates `release/irx-v1.0.zip` locally.
