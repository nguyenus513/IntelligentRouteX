package com.routechain.v2.decision;

import com.routechain.v2.SchemaVersioned;

import java.util.List;
import java.util.Map;

public record DecisionStageInputV1(
        String schemaVersion,
        String traceId,
        String runId,
        String tickId,
        DecisionStageName stageName,
        Map<String, Object> dispatchContext,
        Map<String, Object> candidateSet,
        Map<String, Object> referenceFrame,
        Map<String, Object> comparisonPack,
        Map<String, Object> geospatialContext,
        Map<String, Object> burstContext,
        Map<String, Object> constraints,
        Map<String, Object> contextSelection,
        Map<String, Object> upstreamSummary,
        Map<String, Double> objectiveWeights,
        List<String> upstreamRefs) implements SchemaVersioned {

    public DecisionStageInputV1 {
        dispatchContext = dispatchContext == null ? Map.of() : Map.copyOf(dispatchContext);
        candidateSet = candidateSet == null ? Map.of() : Map.copyOf(candidateSet);
        referenceFrame = referenceFrame == null ? Map.of() : Map.copyOf(referenceFrame);
        comparisonPack = comparisonPack == null ? Map.of() : Map.copyOf(comparisonPack);
        geospatialContext = geospatialContext == null ? Map.of() : Map.copyOf(geospatialContext);
        burstContext = burstContext == null ? Map.of() : Map.copyOf(burstContext);
        constraints = constraints == null ? Map.of() : Map.copyOf(constraints);
        contextSelection = contextSelection == null ? Map.of() : Map.copyOf(contextSelection);
        upstreamSummary = upstreamSummary == null ? Map.of() : Map.copyOf(upstreamSummary);
        objectiveWeights = objectiveWeights == null ? Map.of() : Map.copyOf(objectiveWeights);
        upstreamRefs = upstreamRefs == null ? List.of() : List.copyOf(upstreamRefs);
    }

    public DecisionStageInputV1 withContextSelection(Map<String, Object> newContextSelection) {
        return new DecisionStageInputV1(
                schemaVersion,
                traceId,
                runId,
                tickId,
                stageName,
                dispatchContext,
                candidateSet,
                referenceFrame,
                comparisonPack,
                geospatialContext,
                burstContext,
                constraints,
                newContextSelection,
                upstreamSummary,
                objectiveWeights,
                upstreamRefs);
    }

    public DecisionStageInputV1 withComparisonPack(Map<String, Object> newComparisonPack) {
        return new DecisionStageInputV1(
                schemaVersion,
                traceId,
                runId,
                tickId,
                stageName,
                dispatchContext,
                candidateSet,
                referenceFrame,
                newComparisonPack,
                geospatialContext,
                burstContext,
                constraints,
                contextSelection,
                upstreamSummary,
                objectiveWeights,
                upstreamRefs);
    }

    public DecisionStageInputV1 withBurstContext(Map<String, Object> newBurstContext) {
        return new DecisionStageInputV1(
                schemaVersion,
                traceId,
                runId,
                tickId,
                stageName,
                dispatchContext,
                candidateSet,
                referenceFrame,
                comparisonPack,
                geospatialContext,
                newBurstContext,
                constraints,
                contextSelection,
                upstreamSummary,
                objectiveWeights,
                upstreamRefs);
    }

    public DecisionStageInputV1 withUpstreamSummary(Map<String, Object> newUpstreamSummary) {
        return new DecisionStageInputV1(
                schemaVersion,
                traceId,
                runId,
                tickId,
                stageName,
                dispatchContext,
                candidateSet,
                referenceFrame,
                comparisonPack,
                geospatialContext,
                burstContext,
                constraints,
                contextSelection,
                newUpstreamSummary,
                objectiveWeights,
                upstreamRefs);
    }
}
