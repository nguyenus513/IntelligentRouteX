# Phase 11 Bounded Ejection Search

## Result

Phase 11 target gate is `PASS_WITH_LIMITS`.

- Gate artifact: `artifacts/benchmark/community-phase11-gap-gate-v3/phase10_gap_reduction_gate.md`
- Target artifact: `artifacts/benchmark/community-phase11-gap-targets-v3/`
- Baseline gap sum: `5`
- Candidate gap sum: `5`
- Total gap delta: `0`
- Blockers: `[]`
- Runtime: all target rows under `15s`
- Hard violations: `0`

## What Changed

- Added bounded pair-aware ejection search scaffolding for PDPTW.
- Added receiver-route shortlist and beam caps for pair insertion.
- Added large-instance guard with explicit trace reason `scalable-pair-ejection-deferred-for-large-instance` to prevent official PDPTW timeout.
- Tested expanded VRPTW/PDPTW search; rolled back unsafe larger route elimination budgets because they increased runtime without reducing vehicle gap.

## Target Evidence

| Suite | Instance | Gap B/C | Runtime ms | Trace Attempts | Main Reject Reasons |
|---|---|---:|---:|---:|---|
| Solomon | RC101 | 2/2 | 12759 | 32 | `route-too-large-for-v1`, `route-too-large-for-block`, `no-feasible-insertion` |
| Li & Lim | LR101 | 1/1 | 13528 | 21 | `scalable-pair-ejection-deferred-for-large-instance`, `route-too-large-for-block` |
| Li & Lim | LRC101 | 2/2 | 12083 | 17 | `scalable-pair-ejection-deferred-for-large-instance`, `route-too-large-for-block` |

## Next Required Work

Strict gap reduction now needs a stronger offline route-pool source rather than more blind hot-path insertion scans:

1. PyVRP/HGS route-pool seeding for RC/LR/LRC target instances.
2. Route-pool set partitioning over imported high-quality routes.
3. Scalable PDPTW pair-ejection with precomputed feasible pair-to-route insertion candidates.
4. Cross-exchange for VRPTW with time-window slack pruning.
