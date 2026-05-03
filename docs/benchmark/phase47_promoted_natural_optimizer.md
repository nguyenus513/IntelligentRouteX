# Phase 49: Promoted Natural PDPTW Optimizer Diagnostic

Phase 49 promotes the Phase 47 adaptive-budget natural optimizer as the default diagnostic path for production-natural PDPTW optimization work.

## Promoted Runner

Use:

```powershell
py -3.13 scripts/run_phase47_adaptive_budget_natural_optimizer.py `
  --instances lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8 `
  --data-source auto `
  --mode academic_certification `
  --time-limit 30s `
  --output-dir artifacts/benchmark/community-phase47-adaptive-budget-vehicle-losses-v1
```

Promotion evidence:

- Phase 48 artifact: `artifacts/benchmark/community-phase48-promotion-v2`
- Phase 47 artifact: `artifacts/benchmark/community-phase47-adaptive-budget-vehicle-losses-v1`
- Phase 45 comparison artifact: `artifacts/benchmark/community-phase45-budgeted-vehicle-losses-v3`

## Promotion Result

Phase 48 recommends `phase47` because it improves quality with the same safety profile.

Safety comparison:

| Metric | Phase 45 | Phase 47 |
|---|---:|---:|
| FAIL | 0 | 0 |
| Hard violations | 0 | 0 |
| Over-budget runs | 0 | 0 |
| Leakage | 0 | 0 |

Quality comparison:

| Metric | Phase 45 | Phase 47 |
|---|---:|---:|
| Vehicle reduction | 2 | 3 |
| PASS_STRONG | 2 | 2 |
| PASS | 1 | 1 |
| Objective improvements | 3 | 3 |

The quality win comes from `LRC106`, where Phase 47 improves from `14 -> 12` vehicles while Phase 45 improves from `14 -> 13`.

## Current Status

Phase 47 on the 8 vehicle-loss cases:

| Verdict | Count |
|---|---:|
| PASS_STRONG | 2 |
| PASS | 1 |
| PASS_WITH_LIMITS | 5 |
| FAIL | 0 |

Notable outcomes:

- `LRC202`: `5 -> 4`, `PASS_STRONG`
- `LRC106`: `14 -> 12`, `PASS_STRONG`
- `LRC281`: infeasible incumbent recovery from `0 -> 94`, `PASS`

## Safety Invariants

The promoted diagnostic path must preserve these invariants:

- no target-K forcing in the production-natural path;
- no comparator/reference/BKS data usage;
- no benchmark instance-name special cases;
- hard violations remain `0` for accepted results;
- `overBudget` remains `false` for the configured budget;
- objective regression is never accepted;
- candidates are accepted only through `NaturalPDPTWObjective` improvement.

Target-K runners remain diagnostic microscopes only. They are not promoted as the production-natural optimization path.

## Next Optimization Direction

Use Phase 46 classifier output before adding more algorithmic work.

Current residual classes include:

- `candidate-cap`;
- `route-count-too-large-skip`;
- `runtime-cap`;
- `feasible-candidate-rejected-by-objective`.

Future work should target these classes inside the Phase 47 budget model instead of re-enabling unbounded stages.
