# Phase 12 Route Pool Seeding

## Result

Phase 12 route-pool target gate is `PASS_WITH_LIMITS`.

- Gate artifact: `artifacts/benchmark/community-phase12-route-pool-gate-v2/phase12_route_pool_gate.md`
- Target artifact: `artifacts/benchmark/community-phase12-route-pool-v2/`
- Total gap delta: `0`
- Seed evidence: `True`
- Blockers: `[]`

## Evidence

| Suite | Instance | Gap B/C | Route Pool | Set Partitioning | Runtime ms | Status |
|---|---|---:|---:|---:|---:|---|
| Solomon | RC101 | 2/2 | 38 | True | 11416 | PASS |
| Li & Lim | LR101 | 1/None | 0 | False | 0 | SKIPPED |
| Li & Lim | LRC101 | 2/None | 0 | False | 0 | SKIPPED |

## What Changed

- Added Phase 12 route-pool target runner using academic max-quality operators for VRPTW.
- Added set-partitioning route-pool gate.
- Bounded the route-pool runner to stay under the 15s target after an initial 18s run.
- PDPTW route-pool seeding is explicit skip-safe until pair-route-pool representation is implemented.

## Technical Conclusion

For `RC101`, route-pool seeding and set partitioning produced evidence (`38` routes, SP solution), but the best solution remains at `16` vehicles vs BKS `14`. This suggests the current pool does not contain the missing BKS-quality route combinations.

## Next Work

Phase 13 should add a stronger offline source:

1. Real PyVRP/HGS VRPTW bridge for Solomon/RC targets if `pyvrp` is available.
2. Import PyVRP/HGS routes into the route-pool set-partitioning model.
3. Add PDPTW pair-route-pool model before trying Li & Lim route-pool seeding.
