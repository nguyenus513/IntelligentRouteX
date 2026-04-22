# Dispatch V2 Gold Contract V1

Gold is train-ready output. It may join outcome labels, but it must never backfill decision-time features from outcome-time rows.

## Required Outputs

- `unified_dispatch_distillation.parquet`
- `selection_score.parquet`

## Unified Dispatch Distillation

Required identity columns:

- `traceId`
- `runId`
- `tickId`
- `stageName`
- `entityType`
- `entityId`
- `candidateId`

Required provenance columns:

- `timeLayer`
- `antiLeakageClass`
- `source`
- `fallbackUsed`
- `missingReason`

Required supervision columns when available:

- `selected`
- `downstreamChosen`
- `score`
- `rank`
- `confidence`
- `teacherTraceCount`
- `teacherKinds`
- `teacherFallbackUsed`
- outcome labels from `dispatch_outcome_canonical`

## Selection Score

Required columns:

- `traceId`
- `runId`
- `tickId`
- `stageName`
- `candidateId`
- `entityType`
- `entityId`
- `selected`
- `downstreamChosen`
- `score`
- `rank`
- `confidence`
- `timeLayer`
- `antiLeakageClass`
- `source`
- `fallbackUsed`
- `missingReason`
- `teacherTraceCount`
- `teacherFallbackUsed`
- `labelQuality`

## No-Backfill Rule

The following fields are outcome-only and must never be written into decision-time rows before the final Gold join:

- `actualPickupTravelTimeSeconds`
- `actualMerchantWaitTimeSeconds`
- `actualDropoffTravelTimeSeconds`
- `totalCompletionTimeSeconds`
- `realizedTrafficDelaySeconds`
- `realizedWeatherModifier`
- `delivered`
- `labelQuality`
