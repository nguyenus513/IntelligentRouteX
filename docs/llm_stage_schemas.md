# Dispatch V2 LLM Stage Schemas

## `stage_input_v1`

Required fields:

- `schemaVersion`
- `traceId`
- `runId`
- `tickId`
- `stageName`
- `dispatchContext`
- `candidateSet`
- `referenceFrame`
- `comparisonPack`
- `geospatialContext`
- `burstContext`
- `constraints`
- `objectiveWeights`
- `upstreamRefs`

## `stage_output_v1`

Required fields:

- `schemaVersion`
- `traceId`
- `runId`
- `tickId`
- `stageName`
- `brainType`
- `providerModel`
- `assessments`
- `selectedIds`
- `meta`

## `meta`

Required baseline fields:

- `latencyMs`
- `confidence`
- `fallbackUsed`
- `validationPassed`
- `appliedSource`

LLM-only additive fields:

- `fallbackReason`
- `requestedEffort`
- `appliedEffort`
- `tokenUsage`
- `retryCount`
- `rawResponseHash`
- `authorityMode`
- `authoritativeStageSet`
- `decisionQualityFlags`
- `contextProfile`
- `overlaySet`
- `contextCompressionApplied`
- `effortSelectionReason`

## Assessment Items

`assessments.items[]` should include:

- `id`
- `score`
- `rank`
- `selected`
- `confidence`
- `reasonCodes`
- `dominanceReasonCodes`
- `regretToBestAlternative`
- `driverFitSummary`
- `routeVectorRefs`
- `geospatialFlags`
- `burstSensitivityFlags`
- `rationale`

## Reason Codes

Reason codes should be short, machine-readable, and additive.

Examples:

- `constraint-window-tight`
- `route-vector-congestion-high`
- `selector-conflict-risk`
- `forecast-demand-shift`
- `fallback-simple-penalty`
