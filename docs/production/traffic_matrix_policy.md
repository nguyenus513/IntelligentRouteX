# Traffic Matrix Policy

Traffic-aware dispatch depends on the quality of `durationMatrix`. Phase 82 treats traffic as an input/fallback layer, not a new routing algorithm.

## Required Traffic Context

`trafficContext` should include:

- `provider`: `synthetic`, `osrm`, `google`, `internal`, or `manual`.
- `generatedAt` and `validUntil`: ISO-8601 timestamps.
- `trafficMode`: `normal`, `peak`, `rain`, `incident`, or `unknown`.
- `multiplier`: traffic duration multiplier.
- `confidence`: value in `[0,1]`.
- `matrixSource`: `live`, `cached`, `synthetic`, or `fallback`.
- `freshnessSeconds` and `maxFreshnessSeconds`.
- `region`.

## Fallback Triggers

Traffic fallback or blocking is required when:

- `durationMatrix` is missing, non-square, negative, or has non-zero diagonal entries;
- matrix freshness exceeds the allowed threshold;
- traffic confidence is below the configured minimum;
- live traffic is required but only cached/synthetic/fallback data is available;
- an active route locked prefix becomes risky under updated traffic.

## Readiness Boundary

Phase 82 improves traffic safety and observability. It does not claim `PRODUCTION_MAIN_READY`; live provider integration, monitoring, alerting, and replay/canary evidence are still required.
