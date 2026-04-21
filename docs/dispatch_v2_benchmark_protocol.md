# Dispatch V2 Benchmark Protocol

This document is the measurement contract for Dispatch V2 performance work. Phase 1 benchmark code and scripts must follow this protocol instead of redefining timing scope or workload semantics ad hoc.

## Canonical Pipeline Scope

Dispatch V2 benchmark timing covers the current 12-stage pipeline only:

1. `eta/context`
2. `order-buffer`
3. `pair-graph`
4. `micro-cluster`
5. `boundary-expansion`
6. `bundle-pool`
7. `pickup-anchor`
8. `driver-shortlist/rerank`
9. `route-proposal-pool`
10. `scenario-evaluation`
11. `global-selector`
12. `dispatch-executor`

Timing starts immediately before `eta/context` and ends immediately after `dispatch-executor`.

Timing must exclude post-dispatch hardening I/O:

- replay recording
- decision-log write
- snapshot persistence
- reuse-state persistence

## Benchmark Authority Machine

Absolute latency numbers are release-authoritative only when produced on one pinned machine profile.

Required recorded fields:

- machine label
- CPU model
- logical core count
- RAM size
- operating system and version
- JDK version

Pinned authority profile for v1:

- machine label: `dispatch-v2-benchmark-authority-v1`
- role: local-first benchmark source of truth

The profile above is the naming contract. Exact hardware values are recorded in benchmark artifacts and should be updated when the authority machine changes.

## Artifact Location And Naming

Benchmark artifacts live under `artifacts/perf/`.

Per-run artifact file names must include:

- baseline id
- workload size
- run mode
- commit SHA or `workspace`
- UTC timestamp

Recommended pattern:

- JSON: `dispatch-perf-<baseline>-<size>-<mode>-<commit>-<timestamp>.json`
- Markdown: `dispatch-perf-<baseline>-<size>-<mode>-<commit>-<timestamp>.md`

Markdown is human summary only. JSON is the canonical machine-readable artifact.

## Warmup And Measurement Rules

Pinned v1 defaults:

- warmup runs: `2`
- measured runs: `5`
- repeatability rule: rerun the same matrix on the same authority machine before trusting a regression claim

Warmup runs prime the JVM and caches. They are not included in published percentiles.

Measured runs are independent dispatch measurements using the requested run mode:

- `cold`: fresh harness, no reuse
- `warm`: restart recoverability path using file-backed state
- `hot`: compatible follow-up dispatch on a warm harness

## Observation Metrics Versus Gates

Protocol metrics are split into two groups.

Release-observed metrics:

- p50/p95/p99 total latency
- p50/p95 per-stage latency
- budget breach rate
- reused stage names
- non-negative `estimatedSavedMs` on compatible hot runs

Observation-only metrics in v1:

- memory snapshots
- worker call counts by stage
- live-source call counts by run
- detailed hot-start saved-ms distributions

Observation-only metrics are still required in artifacts, but they are not release-blocking thresholds in Phase 0 + Phase 1.

## Workload Repeatability

Workloads must be deterministic.

Required rules:

- each workload tier is generated from a fixed seed
- seed value is recorded in the artifact
- order count and driver count are recorded in the artifact
- trace ids may vary per run, but request geometry and timing inputs must remain deterministic for the same workload tier

## CI Scope

CI in v1 validates only:

- protocol docs exist
- runner argument handling
- one small smoke benchmark can execute and write artifacts
- artifact schema fields are populated

Full S/M/L/XL benchmark sweeps remain local-first.

## Windows Heavy Harness Mode

Local Windows runs are allowed, but heavy quality-harness cells must be treated as execution-sensitive.

Default rule for Windows heavy cells:

- run cells sequentially
- isolate each cell under its own output root
- finish JSON/Markdown artifact flush for one cell before starting the next
- keep XL deferred unless explicitly enabled

Heavy mode should be used automatically for:

- `local-real` authority diagnostics
- non-`S` workload sweeps
- any run whose purpose is authority evidence rather than quick logic smoke coverage

Artifacts from heavy mode must record:

- execution policy name
- OS profile
- cell start/completion timestamps
- dispatch completion timestamp
- artifact write completion timestamp
- timeout phase classification when a timeout-like failure occurs

Operator checklist for local authority runs:

- use Windows heavy mode on Windows instead of ad hoc parallel sweeps
- inspect timeout classification before treating a failed cell as a logic regression
- inspect promotion blockers for `driver`, `route-critique`, `scenario`, and `route-generation`
