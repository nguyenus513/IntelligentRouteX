# Phase 75 Production Readiness Checklist

## Verdict Levels

- `RESEARCH_ONLY`: useful for experiments, not certification-safe.
- `CERTIFICATION_SAFE`: deterministic, hard-budgeted, no hard violations in certification artifacts.
- `PRODUCTION_CANDIDATE`: safe in benchmark/shadow-mode and has comparator/report evidence.
- `PRODUCTION_MAIN_READY`: has live adapter, fallback, monitoring, replay/canary evidence, and SLA dashboards.

## Algorithm Checklist

- [x] deterministic certification path
- [x] hard wall-clock budget
- [x] no accepted objective regression
- [x] hard violations `0` in current synthetic full report
- [x] overBudget `0` in current synthetic full report

## Benchmark Checklist

- [x] Li-Lim suite
- [x] synthetic food suite
- [x] VROOM comparator
- [x] VROOM time-window audit
- [ ] full stress sensitivity real runs
- [ ] measured ablation real runs

## Production Checklist

- [ ] live orders/drivers/activeRoutes adapter
- [ ] fallback policy if solver fails or times out
- [ ] rollback/canary policy
- [ ] runtime + hard violation monitoring
- [ ] replay logs
- [ ] SLA/tail latency dashboard
- [ ] alerting

## Current Verdict

Current status: `CERTIFICATION_SAFE` and `PRODUCTION_CANDIDATE` for synthetic feasibility/shadow-mode evaluation.

Do **not** mark `PRODUCTION_MAIN_READY` until live adapter, fallback policy, replay evidence, and monitoring are complete.
