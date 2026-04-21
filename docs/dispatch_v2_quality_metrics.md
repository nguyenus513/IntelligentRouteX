# Dispatch V2 Quality Metrics

This document freezes the Phase 2 quality metric contract for benchmark and ablation work.

Phase 2 must derive metrics from existing Dispatch V2 runtime outputs only. It must not widen runtime contracts or invent new production-facing signals.

## Pinned Metrics

- `selectedProposalCount`
- `executedAssignmentCount`
- `conflictFreeAssignments`
- `bundleRate`
- `averageBundleSize`
- `routeFallbackRate`
- `averageProjectedPickupEtaMinutes`
- `averageProjectedCompletionEtaMinutes`
- `landingValueAverage`
- `robustUtilityAverage`
- `selectorObjectiveValue`
- `routeCostQuality`
- `driverEntryQuality`
- `burstRobustness`
- `degradeRate`
- `workerFallbackRate`
- `liveSourceFallbackRate`

## Derivation Rules

- `selectedProposalCount` comes from `GlobalSelectionResult.selectedCount`.
- `executedAssignmentCount` comes from `DispatchExecutionSummary.executedAssignmentCount`.
- `conflictFreeAssignments` is computed from final executed assignments only.
- `bundleRate` is the share of executed assignments with more than one order.
- `averageBundleSize` is computed only across executed bundled assignments and is `0.0` when none exist.
- `routeFallbackRate` is derived from route proposals or assignments carrying fallback route signals already present in runtime outputs.
- `averageProjectedPickupEtaMinutes` and `averageProjectedCompletionEtaMinutes` come from executed assignments.
- `landingValueAverage` and `robustUtilityAverage` come from `RobustUtility`.
- `selectorObjectiveValue` comes from `GlobalSelectionResult.objectiveValue`.
- `routeCostQuality` compares selected route cost against the best available route cost in the same proposal pool.
- `driverEntryQuality` summarizes selected proposal driver-fit quality from the driver shortlist stage.
- `burstRobustness` summarizes how well selected proposals preserve value under stressed scenario outcomes.
- `degradeRate` is observation-only in raw dispatch outputs and is aggregated across sampled dispatches.
- `workerFallbackRate` comes from `MlStageMetadata.fallbackUsed`.
- `liveSourceFallbackRate` comes from `LiveStageMetadata.fallbackUsed`.

## Proxy Language

- “lateness proxy” is represented by `averageProjectedCompletionEtaMinutes`.
- “cancel-risk proxy” is deferred in Phase 2 because the repo does not yet expose a stable existing signal that can be used without changing runtime contracts.

## Observation-Only Notes

These metrics support comparison and tuning, but Phase 2 must keep observation-only notes separate from benchmark conclusions:

- raw degrade reasons
- applied ML source models
- applied live source names
- non-authoritative `local-real` run notes
