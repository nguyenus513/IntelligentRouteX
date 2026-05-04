# Phase 56F Stable Certification Runner

Phase 56F promotes the stable replay runner for certification and shadow-mode diagnostics. It is the strict wall-clock and deterministic certification path, not a claim that it beats the Phase 47 research-quality baseline on every quality metric.

## Promoted Role

- **Certification/shadow-mode runner**: `scripts/run_phase56b_stable_promoted_runner.py --stable-incumbent-replay`
- **Research-quality baseline**: `scripts/run_phase47_adaptive_budget_natural_optimizer.py`
- **Promotion artifact**: `artifacts/benchmark/community-phase56f-stable-vehicle-losses-v3`

Phase 56F is promoted for stable certification because it keeps first-run wall-clock behavior bounded and repeat outcomes deterministic. Phase 47 remains useful for research quality comparisons, but it is not the strict certification baseline because earlier Phase 56 audits found reproducibility and first-run budget issues.

## Smoke Command

```powershell
py -3.13 scripts/run_phase56b_stable_promoted_runner.py `
  --instances lrc202,lrc106 `
  --repeat 3 `
  --stable-incumbent-replay `
  --time-limit 30s `
  --mode academic_certification `
  --output-dir artifacts/benchmark/community-phase56f-smoke-lrc202-lrc106-v1
```

Expected certification properties:

- `actualRuntimeWithinTolerance = true`
- `overBudgetZero = true`
- `hardViolationsZero = true`
- `duplicateOutcomesStable = true`
- `duplicateFinalSignaturesStable = true`

## 8-Case Certification Command

```powershell
py -3.13 scripts/run_phase56b_stable_promoted_runner.py `
  --instances lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8 `
  --repeat 2 `
  --stable-incumbent-replay `
  --time-limit 30s `
  --mode academic_certification `
  --output-dir artifacts/benchmark/community-phase56f-stable-vehicle-losses-v3
```

Phase 56F 8-case certification result:

| Metric | Result |
|---|---:|
| Gate | `PASS` |
| FAIL | `0` |
| actualRuntimeWithinTolerance | `true` |
| overBudgetZero | `true` |
| hardViolationsZero | `true` |
| duplicateOutcomesStable | `true` |
| duplicateFinalSignaturesStable | `true` |

## Quality Tradeoff

Phase 56F intentionally prioritizes certification safety and deterministic wall-clock behavior over opportunistic quality from expensive first-run stages.

| Instance | Phase 47 Research Baseline | Phase 56F Stable Certification |
|---|---:|---:|
| `LRC202` | `5 -> 4` in the Phase 47 artifact | `5 -> 5` under strict first-run hard budget |
| `LRC106` | `14 -> 12` | `14 -> 12` |

The `LRC202` tradeoff is expected: Phase 56F can skip route-pool work when the hard wall-clock guard predicts a first-run overrun. This makes the result safe and reproducible, but it can forgo the higher-quality route-pool improvement seen in research runs.

## Safety Invariants

The stable certification runner must preserve these invariants:

- no target-K forcing in the production-natural path;
- no comparator/reference/BKS data usage;
- no benchmark instance-name special cases;
- stable incumbent replay is required for certification repeats;
- route-pool budget reserve and hard wall-clock guard are required;
- hard violations remain `0` for accepted results;
- objective regression is never accepted;
- candidates are accepted only through `NaturalPDPTWObjective` improvement.

## Next Step

Use Phase 56F for certification and shadow-mode planning. If quality recovery is needed later, optimize a bounded route-pool fast mode under the same hard wall-clock guard rather than reverting to non-deterministic or over-budget behavior.

