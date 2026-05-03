# Phase 20 Reference Route / Strong Offline Solver

Phase 20 tries to break the persistent `RC101` 16-vehicle incumbent by importing any available reference route and running an offline multi-start solver search.

## Pipeline

- Load seed incumbent and route pool.
- Search local reference solution paths for `RC101`.
- Validate and import reference routes if available.
- Run OR-Tools multi-start with fixed-cost, first-solution, and local-search variants.
- Import feasible offline routes into the route pool.
- Run set partitioning.
- Select best solution by feasibility, vehicle count, and distance.

## Commands

```powershell
py -3.13 scripts/run_phase20_reference_or_offline_solver.py --output-dir artifacts/benchmark/community-phase20-reference-offline-v1 --seed-dir artifacts/benchmark/community-phase18-time-window-restructuring-v1 --time-limit 60s --data-source auto --max-runs 12
py -3.13 scripts/build_phase20_reference_or_offline_solver_gate.py --candidate-dir artifacts/benchmark/community-phase20-reference-offline-v1 --output-dir artifacts/benchmark/community-phase20-reference-offline-gate-v1 --time-limit-ms 60000
```

## Gate

- `PASS`: no blockers and vehicle gap decreases.
- `PASS_WITH_LIMITS`: no blockers, no regression, and reference/offline evidence exists.
- `FAIL`: infeasible final result, hard violations, runtime timeout, no evidence, no route-pool expansion, no set-partitioning result, or gap regression.

## Next Step

If this remains `PASS_WITH_LIMITS`, Phase 21 should run the medium benchmark to quantify whole-system behavior while separately sourcing a known `RC101` 14-vehicle reference route for deeper BKS compatibility and seeding.

## Current Result

- Gate artifact: `artifacts/benchmark/community-phase20-reference-offline-gate-v1/phase20_reference_offline_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- `RC101` gap seed/after: `2/2`
- Reference route available/feasible: `false/false`
- Offline runs/feasible runs: `6/3`
- Best offline vehicle count: `16`
- Best observed offline distance: `1710.3173499430034` from `PARALLEL_CHEAPEST_INSERTION + TABU_SEARCH`
- Route pool before/after: `257/267`
- Set partitioning: `true`
- Best final label: `phase20-set-partitioning-reference-offline-pool`
- Runtime: `22018ms`

Offline search improved distance versus the prior incumbent but still did not reduce vehicle count. The missing artifact remains a known `RC101` 14-vehicle reference route or a stronger offline VRPTW solver capable of producing that structure.
