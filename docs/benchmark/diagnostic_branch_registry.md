# Diagnostic Branch Registry

Phase 47 is the promoted production-natural diagnostic optimizer runner:

```powershell
py -3.13 scripts/run_phase47_adaptive_budget_natural_optimizer.py `
  --instances lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8 `
  --data-source auto `
  --mode academic_certification `
  --time-limit 30s `
  --output-dir artifacts/benchmark/community-phase47-adaptive-budget-vehicle-losses-v1
```

Promotion is based on the Phase 48 report: Phase 47 has the same safety as Phase 45 and better vehicle reduction. The production-natural diagnostic path must not use target-K forcing, comparator/reference/BKS data, instance-name policies, or objective-regressing candidates.

## Promoted Runner

| Phase | Runner | Status | Reason |
|---|---|---|---|
| Phase 47 | `scripts/run_phase47_adaptive_budget_natural_optimizer.py` | Promoted | `FAIL=0`, hard violations `0`, over-budget `0`, leakage `0`, total vehicle reduction `3` across the 8 vehicle-loss diagnostics. |

## Diagnostic-Only Branches

| Phase | Runner | Status | Reason Not Promoted |
|---|---|---|---|
| Phase 51 | `scripts/run_phase51_fast_neighborhood_profile.py` | Diagnostic only | Safe, but total vehicle reduction dropped to `2` and LRC202 regressed from `5 -> 4` to `5 -> 5`. |
| Phase 51B | `scripts/run_phase51b_budget_protected_profile.py` | Diagnostic only | Fixed the LRC202 budget-starvation regression, but total vehicle reduction remained `2`, below Phase 47. |
| Phase 52 | `scripts/run_phase52_population_natural_optimizer.py` | Diagnostic only | Safe population route-set generator, but total vehicle reduction remained `2`, below Phase 47. |
| Phase 53 | `scripts/run_phase52_population_natural_optimizer.py` | Diagnostic only | Useful offspring diagnostics and zero unknown blockers, but not a promotion decision over Phase 47. |
| Phase 54A | `scripts/run_phase54a_population_missing_repair.py` | Diagnostic only | Safe missing-repair diagnostics, but total vehicle reduction was `2` and LRC106 regressed versus Phase 47. |

## Promotion Guard

Use the Phase 55 guard before treating any diagnostic branch as a promotion candidate:

```powershell
py -3.13 scripts/run_phase55_promotion_guard.py `
  --baseline-dir artifacts/benchmark/community-phase47-adaptive-budget-vehicle-losses-v1 `
  --candidate-dir <candidate-artifact-dir> `
  --candidate-name <candidate-name> `
  --output-dir artifacts/benchmark/<phase55-output-dir>
```

A candidate can only become a promotion candidate if it preserves Phase 47 safety, covers the same baseline instances, has total vehicle reduction at least as high as Phase 47, and does not regress any instance where Phase 47 improved vehicle count.

