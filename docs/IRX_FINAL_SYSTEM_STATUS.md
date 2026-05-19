# IRX Final System Status

## v0.9.10 ML-guided PD-LNS seed improver

Status: `PASS`

Final gate artifact: `artifacts/test-reports/v0.9.10-ml-guided-pd-lns/final-20case/ml-hybrid-pd-lns-final-summary.json`.

Commits:

- `81fac1354` — ML-guided pickup-delivery destroy/repair.
- `7d1c8a3c9` — no-regress hybrid cross insertion and swap-star.
- `2376f79c2` — final 20-case gate evidence.

Evidence:

- `completed=20/20`
- `overallPass=true`
- `mlBestSeedImprovedCases=19/20`
- `mlGuidedBetterThanHeuristicCases=6/20`
- `hybridWorseThanAutoCases=0`
- `totalDistanceGainOverBestSeedKm=620.4`
- `lateRegression=0`
- `coverageRegression=0`
- `pickupDropoffViolations=0`
- `capacityViolations=0`
- `dominanceFailures=0`

Safe claim:

IRX v0.9.10 uses ML-guided Hybrid PD-LNS to improve the best available seed at pickup/dropoff sequence level. On the 20-case final gate, it improves the best seed in 19/20 cases, beats heuristic PD-LNS in 6/20 cases, never regresses AUTO, and preserves coverage, lateness, pickup/dropoff precedence, capacity, and dominance.

Claim boundary:

Do not claim HYBRID always beats heuristic PD-LNS or wins on aggregate 20-case gain. The final evidence records `totalHybridGainKm=404.5` and `totalHeuristicGainKm=429.7`.
