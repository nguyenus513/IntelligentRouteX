# Phase 10 Vehicle Gap Reduction

## Result

Phase 10 target gate is `PASS_WITH_LIMITS`.

- Gate artifact: `artifacts/benchmark/community-phase10-gap-gate-v3/phase10_gap_reduction_gate.md`
- Target artifact: `artifacts/benchmark/community-phase10-gap-targets-v3/`
- Baseline gap sum: `5`
- Candidate gap sum: `5`
- Total gap delta: `0`
- Hard violations: `0`
- Runtime blockers: `0`
- Trace blockers: `0`

## Target Rows

| Suite | Instance | Gap Baseline/Candidate | Runtime ms | Trace Attempts | Main Reject Reasons |
|---|---|---:|---:|---:|---|
| Solomon | RC101 | 2/2 | 12715 | 32 | `route-too-large-for-v1`, `route-too-large-for-block`, `no-feasible-insertion` |
| Li & Lim | LR101 | 1/1 | 13505 | 21 | `instance-too-large-for-pair-v1`, `route-too-large-for-block`, `no-feasible-block-insertion` |
| Li & Lim | LRC101 | 2/2 | 12092 | 17 | `instance-too-large-for-pair-v1`, `route-too-large-for-block`, `no-feasible-block-insertion` |

## Implementation

- Added Phase 10 target runner for known gap cases.
- Added Phase 10 gap reduction gate comparing Phase 9 baseline against candidate artifacts.
- Enabled consolidation traces for PDPTW in the external benchmark adapter.
- Added bounded `PairAwareRouteEliminationOperator` for PDPTW. Large official PDPTW instances now emit bounded blocker trace instead of exceeding runtime.

## Next Optimization Target

Strict vehicle gap reduction still needs deeper operators:

1. VRPTW `RC101`: cross-exchange/ejection that can move stops from larger routes, not only eliminate small routes.
2. PDPTW `LR101/LRC101`: scalable pair-aware ejection chain with route-level candidate pruning before pair insertion scan.
3. Add route-pool seeding from PyVRP/HGS or max-quality academic solver for these specific target instances.
