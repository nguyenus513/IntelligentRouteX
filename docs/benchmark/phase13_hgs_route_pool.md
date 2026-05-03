# Phase 13 HGS Route Pool

## Result

Phase 13 HGS route-pool gate is `PASS_WITH_LIMITS`.

- Capability artifact: `artifacts/benchmark/phase13-pyvrp-capability/pyvrp_capability.md`
- Target artifact: `artifacts/benchmark/community-phase13-hgs-route-pool-v6/`
- Gate artifact: `artifacts/benchmark/community-phase13-hgs-route-pool-gate-v6/phase13_hgs_route_pool_gate.md`
- PyVRP status: available (`0.13.3`)
- HGS evidence: `True`
- Blockers: `[]`
- Runtime: `12919ms`
- Hard violations: `0`

## Target Evidence

| Suite | Instance | Gap B/C | Pool | HGS Status | HGS Vehicles | HGS Imported | SP | Runtime ms |
|---|---|---:|---:|---|---:|---:|---:|---:|
| Solomon | RC101 | 2/2 | 38 | PASS | 22 | 22 | True | 12919 |
| Li & Lim | LR101 | n/a | 0 | deferred | n/a | n/a | False | 0 |
| Li & Lim | LRC101 | n/a | 0 | deferred | n/a | n/a | False | 0 |

## Implementation

- Added PyVRP capability probe.
- Added real VRPTW PyVRP bridge with normalized Solomon matrix/time-window conversion.
- Imported HGS routes into the existing route pool.
- Ran set partitioning over merged OR-Tools/operator/HGS route pool.
- Fixed PyVRP model issues:
  - self-loop distance/duration set to zero.
  - edge duration no longer double-counts service time.
- Bounded Phase 13 runtime under 15s.

## Conclusion

HGS route import works, but the current PyVRP model returns a 22-vehicle solution for `RC101`, so set partitioning keeps the stronger OR-Tools/operator incumbent at 16 vehicles. The gap remains 2.

## Next Work

Phase 14 should focus on PyVRP model quality:

1. Calibrate PyVRP objective/fleet minimization so HGS competes on vehicle count before distance.
2. Test alternative PyVRP demand/time-window scaling and fixed-cost strategy.
3. Export HGS diagnostics and compare PyVRP feasibility/objective against checker feasibility.
4. If PyVRP remains weak on Solomon, use OR-Tools multi-start route pool with stronger route elimination/cross-exchange instead.
