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

## v0.9.10-C tri-model fusion

Status: `PASS`

Artifacts:

- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/fusion-5case/tri-model-fusion-summary.json`
- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/ablation-5case/tri-model-causal-ablation-summary.json`
- `artifacts/test-reports/v0.9.10-C-tri-model-fusion/tri-model-decision-report.json`

Evidence:

- `forecastCalledCases=0`
- `tabularCalledCases=5/5`
- `routefinderCalledCases=5/5`
- `greedRlCalledCases=5/5`
- `fusionWorseThanBestSingleModelCases=0`
- `fusionBetterThanBestSingleModelCases=1/5`
- `totalFusionGainKm=98.3`
- `totalBestSingleModelGainKm=96.5`
- `modelWorkersWithContribution=3`
- `pickupDropoffViolations=0`
- `capacityViolations=0`
- `lateRegression=0`
- `coverageRegression=0`
- `dominanceFailures=0`

Module decisions:

- Adaptive Policy: `KEEP_CORE`
- Tabular: `KEEP_MODEL_STATIC`
- RouteFinder: `KEEP_OPTIONAL_PROVIDER`
- GreedRL: `KEEP_CONTROLLER_SELECTED`
- Forecast: `OFF_STATIC_LIVE_RESCUE_ONLY`

Claim boundary:

Static PD-LNS fuses three ML contributors: Tabular, RouteFinder, and GreedRL. Forecast is intentionally disabled for static seed improvement because static quality/risk gain was not proven.
