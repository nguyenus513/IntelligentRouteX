# Phase 85 Operator Failure Analysis

Phase 85 records bounded operator failure reasons:

- `objective-not-improved`
- `hard-violation`
- `lock-violation`
- `candidate-cap`
- `runtime-cap`

The expected early result is safety-first: some suites may show `PASS_WITH_LIMITS` until operator ROI produces accepted candidates on larger official runs.

No VROOM, BKS, or reference route is allowed in the operator pool.
