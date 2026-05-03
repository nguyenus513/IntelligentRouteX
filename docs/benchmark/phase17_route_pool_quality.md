# Phase 17 Route-Pool Quality Gap Reduction

Phase 17 targets the remaining `RC101` vehicle-gap bottleneck after Phase 16 fixed short-budget parity.

## Goal

- Audit whether the route pool contains enough coverage/diversity to let set partitioning reduce vehicle count.
- Expand the route pool with bounded targeted variants instead of brute-force search.
- Pass strictly only if vehicle gap improves; otherwise produce actionable diagnostics for the next algorithm phase.

## Added Diagnostics

- Customer coverage min/median/max.
- Low-coverage customers.
- Route size histogram.
- Merge attempt/success counts.
- Merge reject reasons such as `time-window` or `capacity`.
- Actionable next step.

## Commands

```powershell
py -3.13 scripts/run_phase17_route_pool_quality.py --output-dir artifacts/benchmark/community-phase17-route-pool-quality-v1 --seed-dir artifacts/benchmark/community-phase14-pyvrp-calibration-v1 --time-limit 15s --data-source auto
py -3.13 scripts/build_phase17_route_pool_quality_gate.py --candidate-dir artifacts/benchmark/community-phase17-route-pool-quality-v1 --output-dir artifacts/benchmark/community-phase17-route-pool-quality-gate-v1 --time-limit-ms 15000
```

## Gate

- `PASS`: no blockers and vehicle gap decreases.
- `PASS_WITH_LIMITS`: no blockers and diagnostics are actionable, but gap is unchanged.
- `FAIL`: infeasible, hard violations, runtime timeout, no SP result, pool not expanded, or gap regression.

## Next Step

If this phase remains `PASS_WITH_LIMITS`, Phase 18 should use the diagnostics to build a more structural route generator: giant-tour split, BKS/reference-route importer, or customer-cluster split/merge search.

## Current Result

- Gate artifact: `artifacts/benchmark/community-phase17-route-pool-quality-gate-v1/phase17_route_pool_quality_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- `RC101` gap seed/after: `2/2`
- Route pool before/after: `90/92`
- Set partitioning: `true`
- Runtime: `6040ms`
- Coverage min/median/max: `3/5/7`
- Low-coverage customer count: `0`
- Merge attempts/successes: `200/0`
- Top merge reject reason: `time-window` for all sampled merge attempts

The important finding is that route coverage is no longer the immediate bottleneck. The pool has coverage for every customer, but simple pairwise route merging is blocked by time-window feasibility. Phase 18 should therefore focus on time-window-aware route restructuring: giant-tour split, split/merge with time-window slack repair, or reference-route import for model mismatch analysis.
