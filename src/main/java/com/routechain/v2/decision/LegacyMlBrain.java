package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

public final class LegacyMlBrain implements DecisionBrain {

    @Override
    public DecisionStageOutputV1 evaluateStage(DecisionStageInputV1 input) {
        long startedAt = System.nanoTime();
        List<String> selectedIds = selectIds(input.candidateSet());
        List<Map<String, Object>> items = java.util.stream.IntStream.range(0, selectedIds.size())
                .mapToObj(index -> {
                    java.util.LinkedHashMap<String, Object> item = new java.util.LinkedHashMap<>();
                    item.put("id", selectedIds.get(index));
                    item.put("score", Math.max(0.0, 1.0 - (index * 0.05)));
                    item.put("rank", index + 1);
                    item.put("selected", true);
                    item.put("confidence", 1.0);
                    item.put("reasonCodes", List.of("legacy-baseline"));
                    item.put("dominanceReasonCodes", List.of());
                    item.put("regretToBestAlternative", 0.0);
                    item.put("driverFitSummary", "legacy-heuristic");
                    item.put("routeVectorRefs", List.of(selectedIds.get(index)));
                    item.put("geospatialFlags", List.of());
                    item.put("burstSensitivityFlags", List.of());
                    item.put("rationale", "Selected by the legacy deterministic baseline.");
                    return Map.copyOf(item);
                })
                .toList();
        return new DecisionStageOutputV1(
                "stage-output-v1",
                input.traceId(),
                input.runId(),
                input.tickId(),
                input.stageName(),
                DecisionBrainType.LEGACY,
                null,
                Map.of(
                        "summary", "Legacy deterministic baseline output.",
                        "reasonCodes", List.of("legacy-baseline"),
                        "items", items),
                selectedIds,
                DecisionStageMetaV1.legacy(elapsedMs(startedAt)));
    }

    private List<String> selectIds(Map<String, Object> candidateSet) {
        Object topIds = candidateSet.get("topIds");
        if (topIds instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        Object ids = candidateSet.get("ids");
        if (ids instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        return List.of();
    }

    private long elapsedMs(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000L;
    }
}
