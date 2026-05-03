# Phase 16 Gap Reduction

Phase 16 targets the first bottleneck exposed by Phase 15: short-budget benchmark ticks were starving construction search before consolidation could help.

## Change

- For benchmark ticks `<= 5000ms`, `our-dispatch-v2` now uses `short-budget-parity` mode.
- Fixed-cost probe is disabled in short-budget mode.
- Consolidation is disabled in short-budget mode.
- The full tick budget is assigned to construction so `our-dispatch-v2` has parity with `ortools-baseline` on short smoke gates.
- For longer ticks, the existing quality-probe + consolidation path remains enabled.

## Commands

```powershell
py -3.13 scripts/run_phase16_gap_reduction.py --output-dir artifacts/benchmark/community-phase16-gap-reduction-v1 --time-limit 3s --instance-limit 1 --data-source auto
py -3.13 scripts/build_phase16_gap_reduction_gate.py --candidate-dir artifacts/benchmark/community-phase16-gap-reduction-v1 --output-dir artifacts/benchmark/community-phase16-gap-reduction-gate-v1 --max-runtime-p95-ms 15000
```

## Gate

- `PASS`: no blockers and Phase 15 comparison has at least one win.
- `PASS_WITH_LIMITS`: no blockers and no losses, but gap is not reduced yet.
- `FAIL`: benchmark loss, hard violation, runtime p95 breach, or short-budget mode does not allocate full construction budget.

## Next Step

If Phase 16 remains `PASS_WITH_LIMITS`, Phase 17 should target actual quality gap reduction rather than runtime parity: richer route-pool sources, SP diagnostics for missing customer combinations, and PDPTW pair-route-pool support.

## Current Smoke Result

- Gate artifact: `artifacts/benchmark/community-phase16-gap-reduction-gate-v1/phase16_gap_reduction_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- Phase 15 gate inside Phase 16: `PASS_WITH_LIMITS`
- Wins/ties/losses: `0/1/0`
- Blockers: `[]`
- `RC101`: `16` vehicles, budget mode `short-budget-parity`, construction budget `3000ms`, consolidation `0ms`

This fixes the Phase 15 smoke loss caused by construction-budget starvation. It does not reduce the vehicle gap yet; Phase 17 should now focus on route-pool quality and missing BKS-style combinations.
