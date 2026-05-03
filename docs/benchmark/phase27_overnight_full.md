# Phase 27 Overnight Full Large Benchmark

Phase 27 is the first full large community overnight run after shard20 and shard60 passed. It is a release-readiness benchmark, not a smoke test.

## Command

```powershell
py -3.13 scripts/run_phase15_large_benchmark.py --tier large --solvers our-dispatch-v2,ortools-baseline --time-limit 30s --data-source auto --output-dir artifacts/benchmark/community-phase27-overnight-full-v1
py -3.13 scripts/build_phase15_large_benchmark_report.py --input-dir artifacts/benchmark/community-phase27-overnight-full-v1 --output-dir artifacts/benchmark/community-phase27-overnight-full-report-v1
py -3.13 scripts/build_phase15_large_benchmark_gate.py --input-dir artifacts/benchmark/community-phase27-overnight-full-report-v1 --output-dir artifacts/benchmark/community-phase27-overnight-full-gate-v1 --max-runtime-p95-ms 60000 --max-evidence-gap-rate 0.30 --max-wall-clock-overrun-rate 0.0
```

## Result

- Gate artifact: `artifacts/benchmark/community-phase27-overnight-full-gate-v1/phase15_large_benchmark_gate.md`
- Report artifact: `artifacts/benchmark/community-phase27-overnight-full-report-v1/phase15_large_benchmark_report.json`
- Completed cells: `720/720`
- Target instances: `360`
- Solvers: `our-dispatch-v2`, `ortools-baseline`
- Time limit: `30s`
- Verdict: `FAIL`
- Wins/ties/losses: `31/310/19`
- Hard violations: `0`
- Wall-clock overrun rate: `0.0`
- Runtime p50/p95/p99: `31837/34866/36042ms`
- Feasible rows: `334/360`
- Evidence gaps: `26`
- Vehicle gap sum: `3`

## Interpretation

Runtime and feasibility are not the current blockers. The full overnight blocker is route quality on hard Li-Lim cases, especially mixed `LRC` cases.

The main loss classes are:

1. **Vehicle-count losses**: `8` cases use one more vehicle than baseline. These are serious because benchmark comparison prioritizes vehicle count before distance.
2. **Distance losses**: `11` cases use the same vehicle count but have distance above the `1%` same-vehicle tolerance.
3. **Evidence gaps**: `26` Li-Lim cells lack usable solver evidence and reduce full-benchmark confidence.

## Current Bottlenecks

- LRC route-count repair is not strong enough for full overnight.
- Cross-route pair relocation and route ejection need stronger bounded search.
- Same-vehicle distance polish needs targeted improvement for losses above `1%`.
- Evidence fallback needs improvement for Li-Lim cases where no usable solution is returned.

## Next Phase

Before another overnight run:

1. run a targeted subset containing the `19` loss cases;
2. improve LRC route ejection and pair-aware regret insertion;
3. improve bounded distance polish for same-vehicle losses;
4. rerun shard20 and shard60 as regression gates;
5. only rerun full overnight after targeted loss cases improve without runtime regression.
