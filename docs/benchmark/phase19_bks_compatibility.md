# Phase 19 BKS / Reference Compatibility Audit

Phase 19 checks whether the persistent `RC101` gap is caused by solver weakness or benchmark/model compatibility issues.

## Audit Scope

- Instance fingerprint: node count, capacity, depot time window, checksum, BKS metadata.
- Distance semantics: float, integer rounding, floor, ceil, one-decimal, truncated one-decimal, current scaled mode.
- Checker semantics: depot due/service and epsilon variants.
- Reference route lookup in local reference-solution directories.

## Commands

```powershell
py -3.13 scripts/audit_phase19_bks_compatibility.py --output-dir artifacts/benchmark/community-phase19-bks-compatibility-v1 --instance RC101 --data-source auto --incumbent-solution artifacts/benchmark/community-phase18-time-window-restructuring-v1/solomon/RC101/solution.json
py -3.13 scripts/build_phase19_bks_compatibility_gate.py --candidate-dir artifacts/benchmark/community-phase19-bks-compatibility-v1 --output-dir artifacts/benchmark/community-phase19-bks-compatibility-gate-v1
```

## Gate

- `PASS`: feasible reference route exists and validates under current model.
- `PASS_WITH_LIMITS`: audit complete but reference route is missing or not enough to prove BKS compatibility.
- `FAIL`: missing fingerprint, distance semantics, checker semantics, feasible incumbent, or conclusion.

## Next Step

If the result is `PASS_WITH_LIMITS` because reference routes are missing, Phase 20 should obtain/import a known `RC101` 14-vehicle route or run a stronger offline solver with reference-grade output. If a reference route is infeasible, Phase 20 should audit parser/service/distance semantics against the reference arrival trace.

## Current Result

- Gate artifact: `artifacts/benchmark/community-phase19-bks-compatibility-gate-v1/phase19_bks_compatibility_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- BKS metadata: `14` vehicles, objective `1696.94`, source `SINTEF Solomon 100 customers BKS`
- Incumbent: `16` vehicles, distance `1740.020348935445`
- Distance modes audited: `7`
- Checker modes audited: `6`
- Reference route available: `false`
- Conclusion: `model-compatible-reference-route-missing-solver-gap-likely`
- Recommended next step: `obtain-or-generate-reference-14-vehicle-route-file-for-rc101`

Distance semantics are stable for the incumbent under float, nearest-int, floor, one-decimal, truncated one-decimal, and scaled-current modes. `ceil` creates time-window violations, so it is not compatible with the current incumbent. Checker epsilon/depot variants do not change incumbent feasibility. The remaining blocker is absence of a known 14-vehicle reference route to prove exact BKS compatibility and seed/audit the route pool.
