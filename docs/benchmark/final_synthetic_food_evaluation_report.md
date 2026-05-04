# Final System Evaluation Report

## Safety

| Metric | Value |
|---|---:|
| Challenger hard violations | 0 |
| Challenger overBudget count | 0 |
| Challenger FAIL count | 0 |
| Runtime p50/p95/p99 ms | 24252.0 / 25113.0 / 25113.0 |

## Quality Vs VROOM

- VROOM comparator counts: `{"vroom-hard-fail": 6}`
- Gap counts: `{"challenger-better-feasibility": 6}`
- Vehicle gap summary: `{"count": 0, "max": null, "mean": null, "min": null, "sum": 0}`
- Distance gap summary: `{"count": 0, "max": null, "mean": null, "min": null, "sum": 0}`

## Robustness

- VROOM timeout count: 0
- VROOM hard-fail count: 6
- Challenger hard-fail count: 0
- Challenger overBudget count: 0

## Phase 67B VROOM Time-Window Audit

Phase 67B audits the six VROOM hard-fail cases by reconstructing route timelines from raw VROOM request/response artifacts and the normalized synthetic instances.

| Audit Classification | Count |
|---|---:|
| vroom-true-time-window-violation | 4/6 |
| matrix-duration-mismatch | 2/6 |
| unknown | 0/6 |

Interpretation:

- `4/6` cases are confirmed true VROOM time-window violations from VROOM step arrivals.
- `2/6` cases are matrix-duration mismatches and are reported separately, not counted as confirmed true VROOM solver failures.
- Because VROOM has no internally feasible synthetic solution in this run, this report supports a feasibility/stability win for Phase 56F, not a full distance/vehicle-count quality superiority claim over VROOM.

## Scenario Analysis

- Synthetic food scenarios available: True
- Scenario count: 6

| Scenario | VROOM Class | Challenger Vehicles | Challenger Distance | Runtime ms |
|---|---|---:|---:|---:|
| lunch_peak | vroom-hard-fail | 2 | 36.24157819305559 | 25113 |
| dinner_peak | vroom-hard-fail | 2 | 50.10808008488571 | 23953 |
| apartment_cluster | vroom-hard-fail | 2 | 42.707627453274824 | 24671 |
| rain_peak | vroom-hard-fail | 2 | 38.03389157110962 | 24324 |
| sparse_suburban | vroom-hard-fail | 1 | 32.02300171827903 | 22492 |
| cancellation_risk | vroom-hard-fail | 2 | 42.28388589535285 | 24252 |

## Final Verdict

- Production-safe: True
- Industry-quality competitive: no
- Main bottlenecks: industry comparator robustness interpretation
- Audit-backed conclusion: Phase 56F is feasible `6/6` with hard violations `0` and overBudget `0`; VROOM hard-fails `6/6`, with Phase 67B confirming `4/6` true time-window violations and `2/6` matrix-duration mismatches.
- Quality conclusion: blocked/inconclusive on synthetic food because VROOM has no feasible solution to compare distance or vehicle count against.
