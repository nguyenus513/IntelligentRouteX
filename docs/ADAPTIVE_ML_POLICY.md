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

## Safety model

- Evaluator owns accept/reject.
- Dominance guard protects final solution quality.
- Late and coverage regressions are not allowed in certified gates.
- Adaptive policy can influence ordering and budget, not bypass constraints.

## Limitations

This is online adaptive policy evidence, not a deep learning model claim. It is certified only on committed gate suites and should be described as adaptive policy/search learning.
