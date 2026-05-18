# Java Thesis Guide

## Suggested title

IntelligentRouteX: An API-first Java dispatch optimization platform with Adaptive ML-guided local search and BigData-lite runtime support.

## Functional requirements

- Static route dispatch.
- Live rolling dispatch cycle.
- Rescue dispatch after disruption.
- BigData-lite batch ingest and paginated output.
- API job lifecycle and result retrieval.
- Artifact/event/metrics visibility.
- Dashboard Playground demo.

## Non-functional requirements

- One-click local startup and shutdown.
- Automated gates for API, Playground, BigData-lite, and one-click flow.
- Request idempotency for creation endpoints.
- Runtime backpressure and rate-limit-style protection.
- No-regression guards for coverage, lateness, and dominance.

## Architecture chapter

Use `docs/ARCHITECTURE.md` as the base. Emphasize:

- Spring Boot API facade.
- Runtime queue/store abstractions.
- Optimizer core and evaluator.
- Adaptive ML policy layer.
- React Playground.
- Evidence artifacts.

## Algorithm chapter

Describe the optimizer as a hybrid dispatch system:

- heuristic and seed-based construction,
- local search/improvement,
- external solver evidence when available,
- Adaptive ML policy for ordering and budget,
- dominance and late/coverage safety guards.

Do not claim guaranteed optimality.

## Adaptive ML chapter

Use `docs/ADAPTIVE_ML_POLICY.md`. Key evidence:

- `QUALITY_SEEKING` completed `20/20` cases.
- `2` improved cases.
- `1.6 km` distance gain.
- `0` loss, late, dominance, and coverage regressions.

## Testing chapter

Use `docs/BENCHMARKS.md` and evidence artifacts:

- final certification summary,
- API contract summary,
- Playground summary,
- BigData-lite summary,
- one-click gate summary.

## Conclusion

The system demonstrates a local production-demo dispatch platform with API contracts, runtime gates, Adaptive ML-guided search, and a usable Playground. Limitations include no distributed production deployment and no claim of globally optimal routes.
