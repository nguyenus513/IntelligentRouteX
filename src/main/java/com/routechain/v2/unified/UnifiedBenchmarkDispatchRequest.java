package com.routechain.v2.unified;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;

public record UnifiedBenchmarkDispatchRequest<T>(
        String schemaVersion,
        String requestId,
        String datasetId,
        String scenarioId,
        String scenarioHash,
        UnifiedDispatchObjectiveProfile objectiveProfile,
        UnifiedDispatchRoutingMode routingMode,
        Supplier<T> runner,
        Map<String, Object> context) {

    public UnifiedBenchmarkDispatchRequest {
        schemaVersion = schemaVersion == null ? "unified-benchmark-dispatch-request/v1" : schemaVersion;
        objectiveProfile = objectiveProfile == null ? UnifiedDispatchObjectiveProfile.FAST_GATE : objectiveProfile;
        routingMode = routingMode == null ? UnifiedDispatchRoutingMode.FAST_GATE_MATRIX_FIRST_SYNTHETIC : routingMode;
        context = context == null ? Map.of() : nullSafeCopy(context);
    }

    private static Map<String, Object> nullSafeCopy(Map<String, Object> context) {
        Map<String, Object> copy = new LinkedHashMap<>();
        context.forEach((key, value) -> copy.put(key, value == null ? "" : value));
        return Map.copyOf(copy);
    }
}
