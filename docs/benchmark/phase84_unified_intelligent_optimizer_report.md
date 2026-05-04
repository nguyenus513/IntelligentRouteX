# Phase 84 Unified Intelligent Optimizer Report

Phase 84 introduces one feature-driven optimizer core for Li-Lim, synthetic food, VROOM capability cases, and production-like live snapshots.

## Principles

- No instance-name hardcode.
- No benchmark-specific optimization branch.
- No target-K forcing.
- No VROOM/BKS/reference route leakage.
- Safety validation rejects hard violations before accepting candidates.
- The system does not claim `PRODUCTION_MAIN_READY`.

## Core Components

- `InstanceFeatureExtractor`
- `UnifiedNaturalObjective`
- `AdaptiveBudgetController`
- `OperatorPortfolio`
- `AdaptiveHyperHeuristic`
- `RoutePoolMemory`
- `AdaptiveRouteSetSelector`
- `LockAwareOptimizer`

Phase 84 is intentionally conservative: it keeps Phase 56F as the safe incumbent and accepts only natural objective improvements from internal candidates.
