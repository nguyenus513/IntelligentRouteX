# IRX Benchmark Methodology

IRX uses separate benchmark profiles so regression checks and quality evidence are not mixed.

## Profiles

- `FAST_GATE`: 7-case stability gate. It validates identity, dominance, late regression, objective wins, and runtime budget.
- `QUALITY_BENCHMARK`: 20-case evidence gate. It uses `QUALITY_ROAD_MATRIX`, enables deeper local search, external contributor checks, and larger seed budgets.

## Objective Semantics

- Raw distance is reported, but it is not the sole win criterion.
- Objective comparison is SLA-first: coverage, hard feasibility, late count, lateness cost, distance, load penalty, final score.
- Late-adjusted distance is reported to explain cases where a shorter baseline route violates SLA.
- A raw-distance loss is not a correctness fail when the baseline has more late orders and IRX preserves late regression `0`.

## Dominance Guard

- Baselines and external solvers are seed contributors.
- Final output is always `IRX ML-Fused Hybrid`.
- If a baseline/external seed is better under the lexicographic objective, IRX must absorb/improve/guard against regression.

## External Solver Rules

- PyVRP emits `PYVRP_SEED` when the local runtime succeeds.
- VROOM emits `VROOM_SEED` only when `VROOM_BASE_URL` or `VROOM_BIN` is configured.
- If VROOM is not configured, status is `EVIDENCE_GAP`; no VROOM win/loss claim is made.
- External solver failures, timeouts, and evidence gaps are diagnostics, not final solver rows.

## Evidence Claims

- Production-demo benchmark claims must come from `QUALITY_BENCHMARK`, not FAST synthetic regression output.
- VROOM results are only claimable when runtime status is `OK` and a seed artifact is produced.
