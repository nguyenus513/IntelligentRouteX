# Current System Weaknesses

This document is the Phase 81 weakness register. It should be updated from `phase81_bottleneck_summary.json` after each audit run.

## Known Weakness Themes

1. Academic Li-Lim quality gaps can still favor VROOM on feasible cases.
2. Strict synthetic food shows strong Phase 56F feasibility, but VROOM quality comparison is blocked when VROOM is infeasible.
3. Active route locking is now enforced, but it can reduce optimization freedom and should be monitored through route churn metrics.
4. VROOM live snapshot compatibility still needs attention when classifications such as `missing-required-nodes`, `import-fail`, or `matrix-duration-mismatch` appear.
5. Stress thresholds are not production proof until replay/canary evidence exists.
6. Food SLA metrics are estimated from route schedules, not real production outcomes.

## Readiness Boundary

The system is a production-candidate for benchmark/shadow-canary engineering. It is not `PRODUCTION_MAIN_READY` until live adapter wiring, fallback execution, monitoring, alerting, SLA dashboards, and replay/canary evidence are complete.
