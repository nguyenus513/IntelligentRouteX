# IRX Final Certification Report

Status: certified demo gate PASS.

## v0.9.2 External Solver Certification

- Tag target: `v0.9.2-certified-external-solvers`.
- Summary: `artifacts/test-reports/v0.9.2-certified-external-solvers/final-certification-summary.json`.
- Backend compile: PASS; dashboard typecheck/build: PASS.
- External solver gate: PASS; PyVRP `COMPLETED`; VROOM `COMPLETED`; both emitted real seed contributors.
- FAST_GATE: PASS; `7/7`; runtime `228474ms`; late regression `0`; dominance failures `0`.
- QUALITY_BENCHMARK: PASS; `20/20`; Distance objective `20W/0T/0L`; OR-Tools objective `15W/5T/0L`; late regression `0`; dominance failures `0`.
- Academic/static: PASS; PDPTW: PASS; live stress: PASS; rescue: PASS.
- Final solver invariant: `IRX_ML_FUSED_HYBRID`.

## v0.9.3 External Dominance Certification

- External dominance guard now rolls back to the best archive seed when the candidate final is worse under `LEXICOGRAPHIC_SLA_STRICT`.
- Raw-s VROOM smoke: IRX ML-Fused Hybrid ties VROOM at `33.5km`, late `0`, coverage `12/12`, with selected source `VROOM_SEED`.
- VROOM subset gate: `1W / 4T / 0L` vs VROOM objective; no losses; all rows passed `externalSeedDominance`.
- Artifact: `artifacts/test-reports/v0.9.3-external-dominance/subset-5-rerun/vroom-win-gate-summary.json`.
- This is the no-loss milestone (`v0.9.3-external-dominance`), not the VROOM-smoke-win milestone.

## Commit and Tag

- Certification commit at run time: `54bf6ad2e`.
- Existing milestone tag: `v0.9.0-production-demo`.
- Certification summary: `artifacts/test-reports/final-certification/final-certification-summary.json`.

## Gate Results

- Backend compile: PASS.
- Dashboard typecheck/build: PASS.
- FAST_GATE: PASS; `7/7`; runtime `222516ms`; late regression `0`; dominance failures `0`.
- QUALITY_BENCHMARK: PASS; `20/20`; Distance objective `20W/0T/0L`; OR-Tools objective `15W/5T/0L`; late regression `0`; dominance failures `0`.
- Academic/static gate: PASS; CVRP-like and VRPTW-like datasets completed.
- PDPTW gate: PASS; pickup-before-dropoff violations `0`; capacity violations `0`.
- External solver gate: PASS; PyVRP `COMPLETED`; VROOM `COMPLETED` in the WSL rerun.
- Live rolling stress: PASS; `4` cycles; stale buffered orders `0`.
- Rescue gate: PASS; late not worse.
- Final solver invariant: `IRX_ML_FUSED_HYBRID`.

## Dataset Groups

- FAST gate: 7 regression scenarios.
- QUALITY gate: 20 mixed static/quality scenarios.
- Academic/static: CVRP-like capacity and VRPTW-like time-window conversions.
- PDPTW: pickup/dropoff ordering, opposite-direction, tight capacity, tight deadline, active-route insertion.

## External Solvers

- PyVRP emitted a real seed in the external smoke gate.
- VROOM emitted a real `VROOM_SEED` after installing VROOM 1.15.0 in WSL Ubuntu 24.04 and setting `VROOM_BIN=tools/vroom/vroom-wsl.cmd`.
- If `VROOM_BIN` or `VROOM_BASE_URL` is not configured, VROOM correctly falls back to `EVIDENCE_GAP` and is not included in win/loss claims.

## Known Limitations

- FAST runtime varies on Windows; strict timing evidence uses the standalone warmed FAST artifact.
- Academic/static gate uses IRX dashboard scenario conversions, not native benchmark file formats.
- PyVRP bridge can emit partial-coverage seeds; IRX objective/dominance guard prevents final regression.

## Artifact Paths

- FAST strict: `artifacts/test-reports/final-system-closeout/fast-rerun-2/clean-cache-gate-summary.json`.
- QUALITY: `artifacts/test-reports/final-certification/quality/clean-cache-gate-summary.json`.
- Academic: `artifacts/test-reports/final-certification/academic/academic-static-gate-summary.json`.
- PDPTW: `artifacts/test-reports/final-certification/pdptw-rerun-3/pdptw-gate-summary.json`.
- External: `artifacts/test-reports/final-certification/external/external-solver-gate-summary.json`.
- External VROOM WSL rerun: `artifacts/test-reports/final-certification/external-vroom-wsl/external-solver-gate-summary.json`.
- Live: `artifacts/test-reports/final-certification/live/live-stress-gate-summary.json`.
- Rescue: `artifacts/test-reports/final-certification/rescue-rerun/rescue-gate-summary.json`.


## v0.9.9 Adaptive ML Quality Seeking

- Tag target: `v0.9.9-adaptive-ml-quality-seeking`.
- Summary: `artifacts/test-reports/adaptive-ml-policy/v0.9.9-quality-seeking-final-summary.json`.
- Final report: `artifacts/test-reports/adaptive-ml-policy/v0.9.9-quality-seeking-final-report.json`.
- QUALITY_SEEKING 20-case sanity: `20/20` completed; improved cases `2`; total distance gain `1.6km`; loss cases `0`; late regression `0`; dominance failures `0`; coverage regression `0`.
- Claim boundary: Adaptive ML is certified for quality-seeking on this evidence suite; evaluator and dominance guard remain final authority.

## v0.9.9.1 IRX API Platform

- Overall: PASS; summary `artifacts/test-reports/v0.9.9.1-api-platform/final-api-platform-summary.json`.
- API contract: `docs/openapi/irx-api-v1.yaml` exposes `/v1/health`, `/v1/version`, static dispatch jobs, live rolling sessions, rescue jobs, and live event stream.
- Static dispatch API: PASS; async job/result facade returns `IRX_ML_FUSED_HYBRID`, metrics, routes, diagnostics, and Adaptive ML policy output.
- Live dynamic API: PASS; session creation, dynamic order buffering, driver telemetry, rolling cycle, active routes, and state query verified.
- Rescue API: PASS; rescue result includes `rescueDominanceGuard` with late/coverage safety.
- Platform guards: idempotency, request validation, tenant guard, API-key guard, and event stream gates PASS.
- Dashboard validation: `npm run typecheck` PASS and `npm run build` PASS.

## v0.9.9.2-irx-production-runtime

- Overall: PASS; summary `artifacts/test-reports/v0.9.9.2-production-runtime/final-production-runtime-summary.json`.
- Runtime store abstractions: PASS; dispatch job, live session, result, idempotency/rate state, and filesystem artifact store MVP are present.
- Queue routing: PASS; lanes `RESCUE`, `LIVE`, `FAST`, `QUALITY`, `BENCHMARK` with priority order `RESCUE > LIVE > FAST > QUALITY > BENCHMARK`.
- Runtime worker MVP: PASS; API job lifecycle exposes queued/running/completed semantics through the facade and persisted result lookup.
- API protection: PASS; tenant guard, API-key guard, idempotency conflict, validation, rate limit, and artifact access gates pass.
- Observability: PASS; `/v1/admin/queues`, `/v1/admin/workers`, and `/v1/admin/metrics` expose queue, worker, rate-limit, artifact, and Adaptive ML metrics.
- Deployment profile: PASS file-level Docker Compose smoke for `irx-api`, `dashboard`, optional `redis`, `postgres`, and `minio` services.
- Dashboard/runtime validation: `compileJava`, dashboard `typecheck`, and dashboard `build` pass.

## v0.9.9.3 BigData-lite API

- Overall: PASS; summary `artifacts/test-reports/v0.9.9.3-bigdata-lite-api/final-bigdata-lite-api-summary.json`.
- Certification scope: BigData-lite API runtime for large-but-light inputs without Kafka/Spark: batch ingest, normalization, async queue lifecycle, backpressure, retry/dead-letter, paginated outputs, split artifacts, event stream, live telemetry coalescing, and runtime metrics.
- Gate evidence: `compileJava=PASS`, `dashboardBuild=PASS`, `batchIngest=PASS`, `normalization=PASS`, `idempotency=PASS`, `queueRouting=PASS`, `backpressure=PASS`, `asyncLifecycle=PASS`, `pagination=PASS`, `artifactOutput=PASS`, `eventLog=PASS`, `eventStream=PASS`, `deadLetter=PASS`, `liveCoalescing=PASS`, `runtimeMetrics=PASS`, `dockerComposeSmoke=PASS`.
- Claim boundary: this is an in-memory BigData-lite MVP with file/artifact-style outputs and runtime diagnostics; Kafka/Spark/Postgres-backed persistence remains later production hardening.
