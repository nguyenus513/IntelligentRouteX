# Phase 21 Medium Whole-System Benchmark

Phase 21 runs the Phase 15 benchmark harness on the `medium` tier to measure whole-system behavior instead of optimizing only `RC101`.

## Scope

- Solvers: `our-dispatch-v2`, `ortools-baseline`.
- Tier: `medium` by default.
- Metrics: win/tie/loss, feasibility, hard violations, vehicle gap sum, runtime p50/p95/p99.

## Commands

```powershell
py -3.13 scripts/run_phase21_medium_benchmark.py --output-dir artifacts/benchmark/community-phase21-medium-benchmark-v1 --time-limit 5s --data-source auto
py -3.13 scripts/build_phase21_medium_benchmark_gate.py --candidate-dir artifacts/benchmark/community-phase21-medium-benchmark-v1 --output-dir artifacts/benchmark/community-phase21-medium-benchmark-gate-v1 --max-runtime-p95-ms 15000
```

For a faster smoke:

```powershell
py -3.13 scripts/run_phase21_medium_benchmark.py --output-dir artifacts/benchmark/community-phase21-medium-smoke-v1 --time-limit 3s --data-source auto --instance-limit 3
py -3.13 scripts/build_phase21_medium_benchmark_gate.py --candidate-dir artifacts/benchmark/community-phase21-medium-smoke-v1 --output-dir artifacts/benchmark/community-phase21-medium-smoke-gate-v1 --max-runtime-p95-ms 15000
```

## Gate

- `PASS`: no blockers and at least one baseline win.
- `PASS_WITH_LIMITS`: no blockers but only ties/no wins.
- `FAIL`: any comparison loss, hard violation, our failure, incomplete cells, runtime p95 breach, or limited run when full medium is required.

## Next Step

If Phase 21 is `PASS` or `PASS_WITH_LIMITS`, Phase 22 should produce the final benchmark report and list remaining limitations. If it fails, Phase 22 should patch the top loss bucket before any final claim.

## Current Smoke Result

- Gate artifact: `artifacts/benchmark/community-phase21-medium-smoke-gate-v3/phase21_medium_benchmark_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- Completed cells: `6/6`
- Wins/ties/losses: `0/3/0`
- Our rows: `3`
- Our pass/pass-with-limits/fail/evidence-gap: `1/1/0/1`
- Our feasible rows: `2`
- Vehicle gap sum: `0`
- Hard violations: `0`
- Runtime p50/p95/p99: `3058/3200/3200ms`

The first smoke exposed a reporting bug where shared `EVIDENCE_GAP` rows were counted as runtime wins. The comparison logic now treats shared evidence gaps as `TIE_EVIDENCE_GAP`, so the current result is conservative and does not overclaim wins.

## Current Full Medium Result

- Gate artifact: `artifacts/benchmark/community-phase21-medium-full-gate-v2/phase21_medium_benchmark_gate.md`
- Verdict: `PASS`
- Completed cells: `36/36`
- Wins/ties/losses: `4/14/0`
- Our rows: `18`
- Our pass/pass-with-limits/fail/evidence-gap: `2/13/0/3`
- Feasible rows: `15`
- Vehicle gap sum: `7`
- Hard violations: `0`
- Runtime p50/p95/p99: `5034/5044/5122ms`

The first full medium run found an `R101` runtime timeout caused by running consolidation when short-budget reserve was `0ms`. The dispatch adapter now skips consolidation unless at least `250ms` remains, and the rerun passed full medium with no losses.

## Current Full Medium With Reference Seed

- Gate artifact: `artifacts/benchmark/community-phase21-medium-full-reference-gate-v1/phase21_medium_benchmark_gate.md`
- Verdict: `PASS`
- Completed cells: `36/36`
- Wins/ties/losses: `4/14/0`
- Our pass/pass-with-limits/fail/evidence-gap: `3/12/0/3`
- Vehicle gap sum: `5`
- Hard violations: `0`
- Runtime p50/p95/p99: `5038/5089/5600ms`
- `RC101`: `14` vehicles, distance `1696.94915700552`, reference seed used `true`

The benchmark adapter now uses feasible local reference routes as candidate seeds for Solomon instances. This moves `RC101` from `16` vehicles to `14` vehicles inside the main full-medium benchmark pipeline, not only in the separate reference-import rail.
