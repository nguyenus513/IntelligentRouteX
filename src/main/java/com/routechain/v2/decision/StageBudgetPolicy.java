package com.routechain.v2.decision;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class StageBudgetPolicy {

    Map<String, Object> budgetFor(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> Map.of("validationOnly", true, "layers", 6);
            case PAIR_BUNDLE -> Map.of("pairs", 12, "bundles", 12, "layers", 6);
            case ANCHOR -> Map.of("bundles", 6, "anchorsPerBundle", 4, "layers", 6);
            case DRIVER -> Map.of("bundles", 4, "driversPerBundle", 8, "layers", 6);
            case ROUTE_GENERATION -> Map.of("bundles", 1, "drivers", 3, "alternatives", 4, "layers", 6);
            case ROUTE_CRITIQUE -> Map.of("routes", 4, "layers", 6);
            case SCENARIO -> Map.of("proposals", 3, "layers", 6);
            case FINAL_SELECTION -> Map.of("proposals", 3, "layers", 6);
            case SAFETY_EXECUTE -> Map.of("assignments", 3, "layers", 4);
        };
    }

    int candidateLimitFor(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> 0;
            case PAIR_BUNDLE -> 12;
            case ANCHOR -> 24;
            case DRIVER -> 32;
            case ROUTE_GENERATION, ROUTE_CRITIQUE -> 4;
            case SCENARIO, FINAL_SELECTION, SAFETY_EXECUTE -> 3;
        };
    }

    @SuppressWarnings("unchecked")
    List<Map<String, Object>> limitedWindow(DecisionStageName stageName, Map<String, Object> candidateSet) {
        Object raw = candidateSet == null ? null : candidateSet.get("window");
        if (!(raw instanceof List<?> rows)) {
            return List.of();
        }
        int limit = candidateLimitFor(stageName);
        return rows.stream()
                .filter(Map.class::isInstance)
                .map(row -> (Map<String, Object>) row)
                .limit(Math.max(0, limit))
                .toList();
    }

    Map<String, Object> appliedBudget(DecisionStageName stageName, int candidateCountSeen) {
        LinkedHashMap<String, Object> budget = new LinkedHashMap<>(budgetFor(stageName));
        budget.put("candidateCountSeen", candidateCountSeen);
        budget.put("candidateLimit", candidateLimitFor(stageName));
        return Map.copyOf(budget);
    }
}
