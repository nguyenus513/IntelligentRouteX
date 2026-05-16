# IRX Final Certification Report

Status: certified demo gate PASS.

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

