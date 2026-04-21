package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

final class BurstContextAssembler {

    Map<String, Object> build(DecisionStageName stageName,
                              Map<String, Object> dispatchContext,
                              Map<String, Object> candidateSet) {
        List<Map<String, Object>> window = rows(candidateSet.get("window"));
        double pressure = safeNumber(dispatchContext.get("supplyDemandRatio"));
        double urgency = average(window, "urgentOrderSurgeScore", "stabilityScore", "score");
        double routeValue = average(window, "routeValue", "robustUtility", "selectionScore", "score");
        double burstProbability = clamp((pressure * 0.5) + (urgency * 0.3) + (routeValue * 0.2));
        return Map.of(
                "stageName", stageName.wireName(),
                "zoneBurstProbability", burstProbability,
                "expectedOrderCountNext5m", Math.max(1.0, safeNumber(dispatchContext.get("openOrderCount")) * (1.0 + burstProbability)),
                "expectedOrderCountNext15m", Math.max(1.0, safeNumber(dispatchContext.get("openOrderCount")) * (1.0 + (burstProbability * 1.5))),
                "urgentOrderSurgeScore", urgency,
                "driverDrainRisk", clamp(pressure),
                "postDropOpportunityScore", clamp(average(window, "landingValue", "routeValue", "robustUtility")),
                "zoneHeatRank", Math.max(1, (int) Math.round(window.size() * Math.max(1.0, pressure))),
                "corridorDemandShiftScore", clamp(average(window, "expectedValue", "robustUtility", "selectionScore")),
                "weatherSensitivity", clamp(safeNumber(dispatchContext.get("weatherBad")) > 0.0 ? 1.0 : 0.25));
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> rows(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return list.stream()
                .filter(Map.class::isInstance)
                .map(row -> (Map<String, Object>) row)
                .toList();
    }

    private double average(List<Map<String, Object>> rows, String... keys) {
        return rows.stream()
                .mapToDouble(row -> firstNumber(row, keys))
                .filter(Double::isFinite)
                .average()
                .orElse(0.0);
    }

    private double firstNumber(Map<String, Object> row, String... keys) {
        for (String key : keys) {
            Object value = row.get(key);
            if (value instanceof Number number) {
                return number.doubleValue();
            }
        }
        return Double.NaN;
    }

    private double safeNumber(Object value) {
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        if (value instanceof Boolean bool) {
            return bool ? 1.0 : 0.0;
        }
        return 0.0;
    }

    private double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }
}
