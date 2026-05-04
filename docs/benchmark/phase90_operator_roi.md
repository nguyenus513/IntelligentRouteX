# Phase 90 Operator ROI

Phase 90C telemetry separates final candidate checks from internal ALNS search iterations.

Key fields:

- `alnsIterations`
- `destroyRepairAttempts`
- `repairSuccesses`
- `intermediateFeasibleStates`
- `worseIntermediateAccepted`
- `improvingIntermediateAccepted`
- `finalCandidatesProduced`
- `finalCandidatesChecked`
- `finalObjectiveImprovingCandidates`
- `bestObjectiveDelta`
- `bestDistanceDelta`
- `bestVehicleDelta`
- `ejectionAttempts`
- `ejectionSuccesses`
- `safeReturn`
- `earlyStopReason`

This identifies whether failure is caused by no destroy/repair attempts, repair failure, no final candidate, or bounded search with no improving final candidate.
