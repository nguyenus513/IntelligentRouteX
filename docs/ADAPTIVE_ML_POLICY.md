# Adaptive ML Policy

Adaptive ML in IRX is a policy layer for search guidance. It does not replace VROOM/PyVRP and does not override evaluator or dominance safety guards.

## Components

- `AdaptiveSeedPolicy`: ranks seed sources based on reward state.
- `AdaptiveOperatorPolicy`: allocates search budget to operators.
- `AdaptiveMovePriority`: scores and orders candidate moves before evaluator work.
- `AdaptiveRewardCalculator`: updates rewards from accepted/rejected outcomes.

## Modes

### TOP_K_ASSISTED

This mode caps evaluated moves and orders candidates by adaptive score. Evidence from v0.9.7 showed move ordering applied, top-K applied, no-loss safety, and quality-neutral efficiency gains.

### QUALITY_SEEKING

This mode expands adaptive budget to seek solution-quality improvements. It still uses fallback and dominance guards to prevent regression.

Evidence from `artifacts/test-reports/adaptive-ml-policy/v0.9.9-quality-seeking-final-summary.json`:

- `overallPass=true`
- `completed=20/20`
- `improvedCases=2`
- `distanceGainKm=1.6`
- `lossCases=0`
- `lateRegressionCount=0`
- `dominanceFailureCount=0`
- `coverageRegressionCount=0`
- `runtimeReductionMs=86789`

Improved datasets in the evidence file:

- `driver-scarcity-case`: `1.1 km` distance gain.
- `clustered-pickups-random-dropoffs`: `0.5 km` distance gain.

## Persistent learning

v0.9.8 evidence certified reward state persistence across rounds for runtime/search efficiency. That does not by itself claim route-quality improvement; v0.9.9 quality-seeking evidence is the route-quality claim boundary.

## v0.9.10 ML-guided PD-LNS seed improver

v0.9.10 adds ML-guided Hybrid Pickup/Delivery LNS as a best-seed improver. External/internal solvers provide seed candidates; the ML policy guides destroy/repair, mutation ordering, and optional cross/swap-star neighborhoods at pickup/dropoff stop-sequence level. The evaluator and dominance guard remain authoritative.

Final evidence: `artifacts/test-reports/v0.9.10-ml-guided-pd-lns/final-20case/ml-hybrid-pd-lns-final-summary.json`.

- `overallPass=true`
- `completed=20/20`
- `mlBestSeedImprovedCases=19/20`
- `mlGuidedBetterThanHeuristicCases=6/20`
- `hybridWorseThanAutoCases=0`
- `totalDistanceGainOverBestSeedKm=620.4`
- `lateRegression=0`
- `coverageRegression=0`
- `pickupDropoffViolations=0`
- `capacityViolations=0`
- `dominanceFailures=0`

Claim boundary: v0.9.10 proves ML-guided Hybrid PD-LNS can improve the best available seed and beats heuristic PD-LNS on 6/20 final-gate cases. It must not be described as always better than heuristic PD-LNS, because total hybrid gain (`404.5 km`) is below total heuristic gain (`429.7 km`) on the same 20-case suite.

## Safety model

- Evaluator owns accept/reject.
- Dominance guard protects final solution quality.
- Late and coverage regressions are not allowed in certified gates.
- Adaptive policy can influence ordering and budget, not bypass constraints.

## Limitations

This is online adaptive policy evidence, not a deep learning model claim. It is certified only on committed gate suites and should be described as adaptive policy/search learning.
