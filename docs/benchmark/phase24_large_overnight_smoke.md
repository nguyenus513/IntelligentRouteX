# Phase 24 Large / Overnight Smoke

Phase 24 runs a large-tier shard before release to check broader benchmark behavior beyond full medium.

## Current Shard Result

- Runner artifact: `artifacts/benchmark/community-phase24-large-shard30-v1/phase15_large_benchmark_results.json`
- Gate artifact: `artifacts/benchmark/community-phase24-large-shard30-gate-v2/phase15_large_benchmark_gate.md`
- Tier: `large`
- Instance limit: `30`
- Solvers: `our-dispatch-v2`, `ortools-baseline`
- Time limit: `3s` per cell
- Completed cells: `60/60`
- Verdict: `PASS`
- Wins/ties/losses: `2/28/0`
- Hard violations: `0`
- Runtime p50/p95/p99: `4554/5628/5744ms`
- Vehicle gap sum: `1`
- Evidence gaps: `20/30` for `our-dispatch-v2`, caused by large Li&Lim instances where both solvers returned `ortools-no-solution` under the 3s smoke budget.

## Interpretation

This is a release smoke, not a full overnight proof. It confirms no losses or hard violations on the first large shard. The high evidence-gap rate is expected for large Li&Lim cases at `3s`; a true overnight run should use larger budgets and `--resume`.

## Full Overnight Command

```powershell
py -3.13 scripts/run_phase15_large_benchmark.py --tier large --solvers our-dispatch-v2,ortools-baseline --time-limit 30s --data-source auto --output-dir artifacts/benchmark/community-phase24-large-overnight-v1 --resume
py -3.13 scripts/build_phase15_large_benchmark_report.py --input-dir artifacts/benchmark/community-phase24-large-overnight-v1 --output-dir artifacts/benchmark/community-phase24-large-overnight-report-v1
py -3.13 scripts/build_phase15_large_benchmark_gate.py --input-dir artifacts/benchmark/community-phase24-large-overnight-report-v1 --output-dir artifacts/benchmark/community-phase24-large-overnight-gate-v1 --max-runtime-p95-ms 60000 --max-evidence-gap-rate 0.30
```

Use `--resume` because the full large tier may take a long time on Windows.
