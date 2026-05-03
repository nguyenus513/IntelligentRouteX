# Phase 18 Time-Window-Aware Restructuring

Phase 18 responds to the Phase 17 finding that route coverage is sufficient but pairwise merges fail because of time windows.

## Change

- Build multiple giant tours: due-time sorted, ready-time sorted, polar sweep, nearest-due neighbor, and route-pool stitch.
- Split each giant tour greedily into feasible time-window/capacity routes.
- Apply bounded boundary repair between adjacent split routes.
- Import feasible split routes into the route pool.
- Re-run set partitioning.

## Commands

```powershell
py -3.13 scripts/run_phase18_time_window_restructuring.py --output-dir artifacts/benchmark/community-phase18-time-window-restructuring-v1 --seed-dir artifacts/benchmark/community-phase17-route-pool-quality-v1 --time-limit 15s --data-source auto
py -3.13 scripts/build_phase18_time_window_restructuring_gate.py --candidate-dir artifacts/benchmark/community-phase18-time-window-restructuring-v1 --output-dir artifacts/benchmark/community-phase18-time-window-restructuring-gate-v1 --time-limit-ms 15000
```

## Gate

- `PASS`: no blockers and vehicle gap decreases.
- `PASS_WITH_LIMITS`: no blockers and split evidence exists, but gap is unchanged.
- `FAIL`: infeasible, hard violations, runtime timeout, no split candidates, no SP result, no route-pool expansion, or gap regression.

## Next Step

If this remains `PASS_WITH_LIMITS`, Phase 19 should audit model/BKS mismatch or use reference route import because time-window-aware split has not found a 15/14-vehicle structure.

## Current Result

- Gate artifact: `artifacts/benchmark/community-phase18-time-window-restructuring-gate-v1/phase18_time_window_restructuring_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- `RC101` gap seed/after: `2/2`
- Route pool before/after: `92/257`
- Split candidates: `4`
- Best split vehicle count: `24`
- Set partitioning: `true`
- Runtime: `1048ms`
- Best split strategy: `route-pool-stitch`

The split pipeline expands route-pool diversity quickly, but naive giant-tour splitting is much weaker than the existing 16-vehicle incumbent. This strongly suggests Phase 19 should stop trying generic splitting and instead audit BKS/reference-route compatibility or use a stronger exact/known-solution import path to determine whether the model, parser, service times, or distance rounding differ from benchmark assumptions.
