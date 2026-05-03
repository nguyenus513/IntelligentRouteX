# Phase 9 Official Benchmark Certification

## Results

| Gate | Artifact | Verdict | Scope |
|---|---|---|---|
| Official inventory | `artifacts/benchmark/community-phase9-inventory/official_inventory.md` | PASS | Solomon 6 parseable, Li & Lim 354 parseable, Homberger 15 deferred |
| Official smoke + OR-Tools | `artifacts/benchmark/community-phase9-official-smoke-gate-v3/community_benchmark_gate.md` | PASS | 6 our-dispatch-v2 rows + 6 OR-Tools baseline rows |
| Official smoke comparison | `artifacts/benchmark/community-phase9-comparison-v3/phase9_baseline_comparison.md` | PASS | our-dispatch-v2: 6 wins, 0 losses vs OR-Tools baseline |
| Official core | `artifacts/benchmark/community-phase9-official-core-gate-v1/community_benchmark_gate.md` | PASS | 15 our-dispatch-v2 official/auto rows |

## Smoke Highlights

- `our-dispatch-v2` hard feasibility: 100%.
- hard violations: 0.
- runtime blockers after optimization: 0.
- baseline comparison: 6/6 wins or runtime wins vs OR-Tools.

## Remaining Optimization Targets

- Solomon `RC101`: vehicle gap 2 against BKS.
- Li & Lim `LR101`: vehicle gap 1 against BKS.
- Li & Lim `LRC101`: vehicle gap 2 against BKS.
- Recommended next operators: route-elimination cross-exchange for VRPTW and pair-aware route-elimination/ejection for PDPTW.

## Runtime Fix Applied

The external benchmark adapter now reserves more post-processing budget before consolidation, preventing official smoke from exceeding the 15s gate while preserving feasibility and benchmark quality.
