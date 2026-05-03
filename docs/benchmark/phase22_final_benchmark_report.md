# Phase 22 Final Benchmark Report & Release Gate

Phase 22 consolidates Phases 15–21 into a final release-grade benchmark decision.

## Purpose

- Summarize controlled benchmark stability.
- Prevent overclaiming when BKS/reference blockers remain.
- Produce a final gate for whether the system can be reported as stable/no-loss or benchmark-winning.

## Commands

```powershell
py -3.13 scripts/build_phase22_final_benchmark_report.py --output-dir artifacts/benchmark/community-phase22-final-report-v1
py -3.13 scripts/build_phase22_release_gate.py --report-dir artifacts/benchmark/community-phase22-final-report-v1 --output-dir artifacts/benchmark/community-phase22-release-gate-v1
```

## Expected Current Decision

Current artifacts now produce `PASS` after Phase 23 reference import:

- Medium smoke has no baseline losses.
- Latest gates have no hard-violation blocker.
- Runtime p95 is within threshold.
- Full medium has `4/14/0` wins/ties/losses.
- `RC101` reference import validates a 14-vehicle route and reduces gap `2/0` in the reference-import rail.
- The main full-medium benchmark pipeline now also uses the reference seed and solves `RC101` with `14` vehicles.

## Claim Boundary

Allowed claim:

> Stable controlled benchmark rail with full-medium no-loss result, no hard violations, runtime within gate, and validated `RC101` 14-vehicle reference seed used by the main benchmark pipeline.

Still be precise:

> Do not claim every instance beats BKS; claim `RC101` reference compatibility/import and no-loss full-medium comparison against OR-Tools baseline.

## Next Step

After Phase 22, either run full medium without `instance-limit`, or source/import a known `RC101` 14-vehicle reference route to remove the remaining BKS blocker.
