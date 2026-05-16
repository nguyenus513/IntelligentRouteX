# IRX Final System Status

Status: production-demo closeout and full certification gates passed after goal-loop rerun.

## Final Gate Evidence

- Compile: `compileJava` PASS.
- Dashboard: `npm run typecheck` PASS, `npm run build` PASS.
- FAST_GATE: 7/7 completed; standalone strict rerun runtime `222516ms`; late regression `0`; dominance failures `0`.
- QUALITY_BENCHMARK: 20/20 completed; runtime `941967ms`; late regression `0`; dominance failures `0`.
- Objective vs Distance: `20W / 0T / 0L`.
- Objective vs OR-Tools: `15W / 5T / 0L`.
- Live stress: PASS; 4 cycles; 35 assigned; 0 buffered stale orders; mode `LIVE_ROLLING`.
- Rescue: PASS after dominance rollback guard; before late `16`, after late `16`; mode `RESCUE`.
- External smoke: PyVRP `COMPLETED`; VROOM `EVIDENCE_GAP` because no runtime configured.
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

## Limitations

- VROOM is contributor-ready but not claimed unless `VROOM_BASE_URL` or `VROOM_BIN` is configured.
- PyVRP seed uses the current VRPTW bridge and may emit partial-coverage seeds; the archive/objective/dominance guard prevents final regression.
- QUALITY_BENCHMARK is intentionally slower than FAST_GATE and is used for evidence, not quick regression.
- Rescue currently applies a dominance rollback guard when a rescue candidate increases late count.

## Run Again

1. Start backend on a port, for example `18116`.
2. Run `powershell.exe -ExecutionPolicy Bypass -File scripts/run-final-system-gate.ps1 -BaseUrl http://localhost:18116`.
3. Inspect `artifacts/test-reports/final-system/final-system-summary.json`.
