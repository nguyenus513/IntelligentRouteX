# Adaptive ML-Bundle Dispatch Layer

## Summary

IntelligentRouteX now includes an Adaptive ML-Bundle Dispatch Layer that turns the dispatch core from rule-based composition into learning-assisted dynamic dispatch. The layer combines Aging-Regret Order Admission, Spatial-Directional Bundle Scoring, Min-Cost Driver-Bundle Matching, Frozen Convenient Insertion, and ALNS-style Destroy-Repair.

The layer uses existing ML signals without adding a new deep model:

- Forecast-style signals -> `lateRisk` and `breakRisk`.
- RouteFinder-style signals -> route sequence quality and insertion quality.
- GreedRL / Adaptive Policy-style signals -> destroy-repair operator priority.

## Algorithm Flow

1. New orders enter the rolling buffer.
2. Aging-regret priority ranks which orders should be handled first.
3. Spatial/directional bundle scoring keeps nearby, same-direction, deadline-compatible bundles.
4. Greedy set packing removes overlapping bundles.
5. Driver-bundle matching chooses the lowest-cost driver assignment.
6. Convenient insertion tries to add orders behind the frozen current stop.
7. Break-risk detection flags unstable bundles.
8. ALNS-style destroy-repair attempts safe repair.
9. No-regress guards reject hard violations, coverage loss, late regressions, and frozen-stop mutation.
10. Feedback telemetry records scores, risks, assignments, repair outcomes, and ML signal usage.

## Demo Metrics

Run:

```powershell
py -3 scripts/run_adaptive_bundle_dispatch_demo.py --output-dir artifacts/benchmark/adaptive_bundle_dispatch_demo
```

The demo emits three scenarios:

| Scenario | Purpose | Key Metrics |
|---|---|---|
| nearby_same_direction_bundle | Nearby + same direction creates a good bundle | `bundleScore`, `assignmentCost`, distance before/after |
| driver_passing_convenient_insertion | Driver already passing nearby picks up extra order | `insertExtraCost`, frozen-stop-safe route |
| bad_bundle_break_risk_destroy_repair | Bad bundle triggers repair before commit | `breakRisk`, `repairSuccess`, late/distance before/after |

## Report Claim

The system adds an Adaptive ML-Bundle Dispatch Layer that combines Aging-Regret Order Admission, Spatial-Directional Bundle Scoring, Min-Cost Driver-Bundle Matching, Frozen Convenient Insertion, and ALNS-style Destroy-Repair. It uses Forecast, RouteFinder, and GreedRL-style signals to optimize order selection, bundle construction, driver assignment, route insertion, and repair before committing routes through a no-regress safety guard.

## Validation

Focused validation:

```powershell
.\gradlew.bat test --tests "com.routechain.v2.bundle.*" --tests "com.routechain.v2.active.*" --tests "com.routechain.v2.repair.*" --no-daemon --console=plain
.\gradlew.bat compileJava --no-daemon --console=plain
```
