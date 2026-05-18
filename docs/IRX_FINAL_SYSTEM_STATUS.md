# IRX Final System Status

Status: production-demo closeout and full certification gates passed after goal-loop rerun.

## v0.9.2-certified-external-solvers

- Overall: PASS; summary `artifacts/test-reports/v0.9.2-certified-external-solvers/final-certification-summary.json`.
- External solvers: PyVRP `COMPLETED`; VROOM `COMPLETED`; reasons `pyvrp-seed-emitted`, `vroom-seed-emitted`.
- FAST_GATE: 7/7 completed; runtime `228474ms`; late regression `0`; dominance failures `0`; Distance objective `7W / 0T / 0L`; OR-Tools objective `4W / 3T / 0L`.
- QUALITY_BENCHMARK: 20/20 completed; runtime `917567ms`; late regression `0`; dominance failures `0`; Distance objective `20W / 0T / 0L`; OR-Tools objective `15W / 5T / 0L`.
- Academic/static: PASS; CVRP-like and VRPTW-like conversions completed.
- PDPTW: PASS; pickup-before-dropoff violations `0`; capacity violations `0`.
- Live stress: PASS; 4 cycles; 35 assigned; 0 buffered stale orders; mode `LIVE_ROLLING`.
- Rescue: PASS; before late `11`; after late `11`; rescued route count `6`.
- Final solver invariant: `IRX_ML_FUSED_HYBRID`.

## v0.9.3-external-dominance

- Goal: IRX final must not lose against VROOM/PyVRP external seeds under the unified objective.
- Raw-s VROOM smoke: PASS; VROOM `33.5km / late0 / 12 of 12`; IRX ML-Fused Hybrid `33.5km / late0 / 12 of 12`; `vsVroomObjective=TIE`; selected seed `VROOM_SEED`.
- VROOM 5-case subset: PASS; `1W / 4T / 0L`; no VROOM objective losses; external dominance passed all rows.
- Artifact: `artifacts/test-reports/v0.9.3-external-dominance/subset-5-rerun/vroom-win-gate-summary.json`.
- New diagnostics: `externalSeedDominance` records best external seed, final seed, rollback source, and `vsVroomObjective` / `vsPyvrpObjective`.
- Limitation: this milestone proves no-loss/absorption, not raw distance win on raw-s; VROOM raw-s remains tied at `33.5km`.

## Final Gate Evidence

- Compile: `compileJava` PASS.
- Dashboard: `npm run typecheck` PASS, `npm run build` PASS.
- FAST_GATE: 7/7 completed; standalone strict rerun runtime `222516ms`; late regression `0`; dominance failures `0`.
- QUALITY_BENCHMARK: 20/20 completed; runtime `941967ms`; late regression `0`; dominance failures `0`.
- Objective vs Distance: `20W / 0T / 0L`.
- Objective vs OR-Tools: `15W / 5T / 0L`.
- Live stress: PASS; 4 cycles; 35 assigned; 0 buffered stale orders; mode `LIVE_ROLLING`.
- Rescue: PASS after dominance rollback guard; before late `16`, after late `16`; mode `RESCUE`.
- External smoke: PyVRP `COMPLETED`; VROOM `COMPLETED` via WSL binary wrapper `tools/vroom/vroom-wsl.cmd`.
- Final solver invariant: `IRX ML-Fused Hybrid` remains the final solver row.
- Academic/static gate: PASS.
- PDPTW gate: PASS; pickup-before-dropoff violations `0`; capacity violations `0`.
- Final certification summary: `artifacts/test-reports/final-certification/final-certification-summary.json`.

## Artifacts

- Final closeout summary: `artifacts/test-reports/final-system-closeout/final-system-summary.json`.
- FAST summary: `artifacts/test-reports/final-system-closeout/fast/clean-cache-gate-summary.json`.
- FAST strict rerun summary: `artifacts/test-reports/final-system-closeout/fast-rerun-2/clean-cache-gate-summary.json`.
- QUALITY summary: `artifacts/test-reports/final-system-closeout/quality/clean-cache-gate-summary.json`.
- Live stress summary: `artifacts/test-reports/final-system-closeout/live-stress/live-stress-gate-summary.json`.
- Rescue rerun summary: `artifacts/test-reports/final-system-closeout/rescue-rerun/rescue-gate-summary.json`.
- External solver smoke: `artifacts/test-reports/final-system-closeout/pyvrp-vroom-smoke-BMJ-044D6247.json`.
- VROOM WSL solver gate: `artifacts/test-reports/final-certification/external-vroom-wsl/external-solver-gate-summary.json`.

## Limitations

- VROOM is now locally available through WSL Ubuntu 24.04 and `VROOM_BIN=tools/vroom/vroom-wsl.cmd`; if that env var is missing, it still reports `EVIDENCE_GAP` by design.
- PyVRP seed uses the current VRPTW bridge and may emit partial-coverage seeds; the archive/objective/dominance guard prevents final regression.
- QUALITY_BENCHMARK is intentionally slower than FAST_GATE and is used for evidence, not quick regression.
- Rescue currently applies a dominance rollback guard when a rescue candidate increases late count.

## Run Again

1. Start backend on a port, for example `18116`.
2. Run `powershell.exe -ExecutionPolicy Bypass -File scripts/run-final-system-gate.ps1 -BaseUrl http://localhost:18116`.
3. Inspect `artifacts/test-reports/final-system/final-system-summary.json`.

## v0.9.9-adaptive-ml-quality-seeking

- Overall: PASS candidate; summary `artifacts/test-reports/adaptive-ml-policy/v0.9.9-quality-seeking-final-summary.json`.
- `QUALITY_SEEKING` differs from `TOP_K_ASSISTED`: it expands adaptive search budget and enables deeper exact reorder to seek solution-quality improvement, not only runtime/search efficiency.
- 5-case gate: PASS; improved cases `1/5`; distance gain `1.1km`; loss `0`; late regression `0`; dominance failures `0`; coverage regression `0`.
- 20-case sanity: PASS; completed `20/20`; improved cases `2/20`; distance gain `1.6km`; loss `0`; late regression `0`; dominance failures `0`; coverage regression `0`.
- Safety model: evaluator still owns accept/reject decisions; adaptive results remain protected by heuristic fallback and dominance guard.

## v0.9.9.1-irx-api-platform

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

## v0.9.9.3-bigdata-lite-api

- Overall: PASS; summary `artifacts/test-reports/v0.9.9.3-bigdata-lite-api/final-bigdata-lite-api-summary.json`.
- Batch ingest: PASS for `100` and `1000` order batches through `/api/v1/ingest/orders/batch`, with strict invalid-row rejection evidence.
- Runtime flow: PASS for `Ingest -> Normalize -> Queue -> Worker -> Store -> Paginate/Stream/Artifact` using `STATIC_QUEUE`, `LIVE_QUEUE`, `RESCUE_QUEUE`, and `DEAD_LETTER_QUEUE`.
- Protection: PASS for idempotency duplicate replay, idempotency conflict, queue backpressure, API-key guard, and path traversal blocking on artifact access.
- Output scale: PASS for summary-only result, routes/assignments/events cursor pagination, artifact listing/download, event log, and SSE progress stream.
- Recovery/observability: PASS for retry-to-dead-letter, DLQ requeue, live telemetry coalescing, runtime state, queue counts, worker status, metrics, and Docker Compose smoke.
- Validation: `compileJava`, dashboard `typecheck`, and dashboard `build` pass in the final BigData-lite gate.

## v0.9.9.4-api-contract-final

- Overall: PASS; summary `artifacts/test-reports/v0.9.9.4-api-contract-final/api-contract-summary.json`.
- Contract envelope: PASS for success/error `{ ok, requestId, data/error, meta }` with stable `NOT_FOUND` and `CONFLICT` checks.
- Job lifecycle: PASS for create/get/result/cancel-conflict and clear links/progress/status fields.
- API groups: PASS for static dispatch, live rolling, rescue, BigData-lite, artifact, event, runtime state, queues, workers, and metrics.
- Idempotency: PASS for same-key replay and same-key/different-payload conflict.
- BigData-lite: PASS for batch ingest, invalid-row normalization, pagination, metrics, and dead-letter visibility.
- Docs: OpenAPI marker coverage plus `docs/API_REFERENCE.md`, `docs/API_EXAMPLES.md`, and `docs/BIGDATA_LITE_API.md` present.

## v0.9.9.5-irx-playground

- Overall: PASS; summary `artifacts/test-reports/v0.9.9.5-irx-playground/playground-summary.json`.
- `/playground` route exists and renders the API-first IRX Playground shell.
- Dashboard validation: `npm run typecheck` PASS and `npm run build` PASS.
- Backend/API flows: static, live, rescue, BigData-lite, events, and artifacts PASS via locked `/api/v1` contracts.
- UI panels: result summary, Adaptive ML diagnostics, baseline comparison, assignment preview, event/artifact list, and raw JSON are present.
