package com.routechain.v2.unified;

import java.util.LinkedHashMap;
import java.util.Map;

public record UnifiedBenchmarkDispatchResult<T>(
        String schemaVersion,
        String requestId,
        String datasetId,
        String scenarioHash,
        UnifiedDispatchObjectiveProfile objectiveProfile,
        UnifiedDispatchRoutingMode routingMode,
        T result,
        Map<String, Object> diagnostics) {

    public UnifiedBenchmarkDispatchResult {
        schemaVersion = schemaVersion == null ? "unified-benchmark-dispatch-result/v1" : schemaVersion;
        objectiveProfile = objectiveProfile == null ? UnifiedDispatchObjectiveProfile.FAST_GATE : objectiveProfile;
        routingMode = routingMode == null ? UnifiedDispatchRoutingMode.FAST_GATE_MATRIX_FIRST_SYNTHETIC : routingMode;
        diagnostics = diagnostics == null ? Map.of() : nullSafeCopy(diagnostics);
    }

    private static Map<String, Object> nullSafeCopy(Map<String, Object> diagnostics) {
        Map<String, Object> copy = new LinkedHashMap<>();
        diagnostics.forEach((key, value) -> copy.put(key, value == null ? "" : value));
        return Map.copyOf(copy);
    }
}
