# IRX Favorable Benchmark Summary

Source: `artifacts/test-reports/v1.0.2.1-irx-benchmark-standard-rerun-strongest`

## Headline

IRX Hybrid/no-regress is zero-loss versus the strongest baseline candidate on the static standard suite and passes official Solomon/LiLim smoke with zero hard violations.

## Strongest Claims

- Static standard: 10/10 PASS
- Static standard: 4 wins / 6 ties / 0 losses versus strongest baseline candidate
- Static standard: 0 late regressions and 0 dominance failures
- Official Solomon/LiLim smoke: IRX feasible 6/6 with 0 hard violations
- Official Solomon/LiLim smoke: 1 win / 5 ties / 0 losses versus OR-Tools
- Dynamic smoke: 5/5 safety PASS with 0 freeze/capacity/pickup-dropoff violations
- ML smoke: 0 losses versus no-ML baseline

## Best Static Wins

| Dataset | IRX km | Baseline km | Advantage km |
|---|---:|---:|---:|
| driver-scarcity-case | 48.7 | 65.3 | 16.6 |
| raw-m | 34.6 | 41.6 | 7 |
| raw-s | 30.2 | 33.5 | 3.3 |
| opposite-direction-dropoffs | 67.5 | 67.9 | 0.4 |

## Official Solomon/LiLim

- IRX feasible: 6/6
- Hard violation rows: 0
- IRX vs OR-Tools: 1W / 5T / 0L

## Boundaries

- Do not claim dynamic latency/churn/SLA win yet.
- Do not claim official PyVRP comparison yet.
- Do not claim BKS no-loss yet.
- Do not claim native-only IRX beats every external solver.
