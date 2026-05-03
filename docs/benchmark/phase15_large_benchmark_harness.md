# Phase 15 Large Benchmark Harness

Phase 15 turns the community benchmark rail into a resumable large-system benchmark harness.

## Goal

- Run fast, gap, medium, or large benchmark tiers with consistent solver/time-limit settings.
- Save each benchmark cell immediately so interrupted runs can resume.
- Aggregate quality, feasibility, vehicle-gap, runtime, and baseline win/loss metrics.
- Gate the result before claiming benchmark progress.

## Commands

```powershell
py -3.13 scripts/run_phase15_large_benchmark.py --tier fast --solvers our-dispatch-v2,ortools-baseline --time-limit 5s --data-source auto --output-dir artifacts/benchmark/community-phase15-large-fast-v1
py -3.13 scripts/build_phase15_large_benchmark_report.py --input-dir artifacts/benchmark/community-phase15-large-fast-v1 --output-dir artifacts/benchmark/community-phase15-large-fast-report-v1
py -3.13 scripts/build_phase15_large_benchmark_gate.py --input-dir artifacts/benchmark/community-phase15-large-fast-report-v1 --output-dir artifacts/benchmark/community-phase15-large-fast-gate-v1 --max-runtime-p95-ms 15000
```

## Tiers

- `fast`: C/R/RC + LC/LR/LRC smoke; best for every algorithm phase.
- `gap`: current weak targets: `RC101`, `LR101`, `LRC101`.
- `medium`: representative official Solomon + Li&Lim set.
- `large`: all discoverable official Solomon + Li&Lim files.

## Gate

- `PASS`: no blockers, no comparison losses, and at least one baseline win.
- `PASS_WITH_LIMITS`: no blockers but no clear win yet.
- `FAIL`: infeasible/failing cell, hard violation, comparison loss, incomplete cells, too much evidence gap, or runtime p95 above threshold.

## Usage Rule

Use Phase 15 before deeper algorithm changes. If the gate is `PASS_WITH_LIMITS`, inspect the aggregate report and make Phase 16 target the top bottleneck instead of guessing.

## Current Smoke Result

- Smoke artifact: `artifacts/benchmark/community-phase15-gap-smoke-gate-v2/phase15_large_benchmark_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- Tier: `gap`, `instance-limit=1`, solvers `our-dispatch-v2,ortools-baseline`
- Wins/ties/losses: `0/1/0`
- Hard violations: `0`
- Our vehicle gap sum: `2`
- Runtime p95: `4342ms`

The first smoke run exposed an overly aggressive short-budget allocator in the dispatch adapter. Construction time was being starved for 3s runs, so the adapter was patched to reserve a bounded post-processing budget instead of forcing a 2500ms minimum reserve on short ticks.
