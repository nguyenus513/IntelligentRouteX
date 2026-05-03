# Phase 14 PyVRP/HGS Calibration

Phase 14 calibrates the real PyVRP/HGS VRPTW bridge before using HGS routes as benchmark-quality route-pool seeds.

## Goal

- Diagnose why Phase 13 HGS produced feasible but weak `RC101` routes.
- Run multiple bounded PyVRP model variants under the same tick-scale budget.
- Import feasible HGS routes into the route pool and solve the reduced set-partitioning model.
- Pass strictly only if vehicle-count gap improves; otherwise pass with limits when calibration evidence is complete and non-regressing.

## Variants

- `duration-service-scale1000`: Phase 13 compatible model.
- `travel-only-scale1000`: avoids double-counting service in edge duration.
- `travel-only-scale100`: checks cost/time scaling sensitivity.
- `travel-only-scale10`: checks smaller integer scale sensitivity.
- `pickup-demand-scale1000`: checks demand semantic sensitivity.

## Commands

```powershell
py -3.13 scripts/run_phase14_pyvrp_calibration.py --output-dir artifacts/benchmark/community-phase14-pyvrp-calibration-v1 --time-limit 15s --hgs-time-limit 8s --data-source auto
py -3.13 scripts/build_phase14_pyvrp_calibration_gate.py --baseline-dir artifacts/benchmark/community-phase13-hgs-route-pool-v6 --candidate-dir artifacts/benchmark/community-phase14-pyvrp-calibration-v1 --output-dir artifacts/benchmark/community-phase14-pyvrp-calibration-gate-v1 --time-limit-ms 15000
```

## Gate

- `PASS`: no blockers and total vehicle-gap delta is positive.
- `PASS_WITH_LIMITS`: no blockers, HGS calibration variants ran, at least one HGS solution passed, and gap did not regress.
- `FAIL`: runtime timeout, infeasible target, no HGS pass, no HGS route-pool evidence, missing target, or gap regression.

## Next Step If Gap Stays Flat

If `RC101` remains at gap `2`, keep PyVRP as an offline diagnostic source and pivot Phase 15 to stronger OR-Tools multi-start + route-pool diversification because current HGS import does not yet contribute BKS-quality route combinations.

## Current Result

- Gate artifact: `artifacts/benchmark/community-phase14-pyvrp-calibration-gate-v1/phase14_pyvrp_calibration_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- Total gap delta: `0`
- `RC101`: baseline/candidate gap `2/2`
- Best HGS variant: `travel-only-scale10`
- Best HGS vehicle count: `18`
- Final selected solution: `16` vehicles from the OR-Tools/operator incumbent
- Route pool grew from `16` to `90` routes and set partitioning produced a solution, but the pool still lacks the missing 15/14-vehicle combinations.
