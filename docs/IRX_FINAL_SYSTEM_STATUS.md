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
