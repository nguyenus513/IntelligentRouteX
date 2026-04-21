package com.routechain.v2.decision;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class ReferenceFrameBuilder {

    Map<String, Object> build(DecisionStageName stageName, Map<String, Object> candidateSet) {
        List<Map<String, Object>> window = rows(candidateSet.get("window"));
        if (window.isEmpty()) {
            return Map.of("stageName", stageName.wireName(), "windowSize", 0);
        }
        LinkedHashMap<String, Object> frame = new LinkedHashMap<>();
        frame.put("stageName", stageName.wireName());
        frame.put("windowSize", window.size());
        frame.put("fastestEta", pickBest(window, "projectedPickupEtaMinutes", "pickupEtaMinutes", "expectedValue"));
        frame.put("lowestCost", pickBest(window, "routeCost", "selectionScore", "score"));
        frame.put("safest", pickBest(window, "congestionScore", "driverFitScore", "stabilityScore"));
        frame.put("closestDriverEntry", pickBest(window, "driverToFirstPickupEtaSeconds", "effectiveDistanceMeters", "pickupEtaMinutes"));
        frame.put("heuristicBaseline", baseline(window));
        frame.put("medianSummary", medianSummary(window));
        return Map.copyOf(frame);
    }

    private Map<String, Object> pickBest(List<Map<String, Object>> window, String... keys) {
        return window.stream()
                .filter(row -> numericValue(row, keys) != Double.POSITIVE_INFINITY)
                .min(java.util.Comparator.comparingDouble(row -> numericValue(row, keys)))
                .map(row -> Map.<String, Object>of(
                        "id", String.valueOf(row.getOrDefault("id", row.getOrDefault("proposalId", row.getOrDefault("driverId", row.getOrDefault("bundleId", ""))))),
                        "metricValue", numericValue(row, keys),
                        "snapshot", row))
                .orElse(Map.of());
    }

    private Map<String, Object> baseline(List<Map<String, Object>> window) {
        Map<String, Object> row = window.get(Math.min(1, window.size() - 1));
        return Map.of(
                "id", String.valueOf(row.getOrDefault("id", row.getOrDefault("proposalId", row.getOrDefault("driverId", row.getOrDefault("bundleId", ""))))),
                "score", numericValue(row, "routeValue", "selectionScore", "score", "robustUtility"));
    }

    private Map<String, Object> medianSummary(List<Map<String, Object>> window) {
        List<Double> scores = window.stream()
                .map(row -> numericValue(row, "routeValue", "selectionScore", "score", "robustUtility"))
                .filter(Double::isFinite)
                .sorted()
                .toList();
        double medianScore = scores.isEmpty() ? 0.0 : scores.get(scores.size() / 2);
        return Map.of(
                "windowCount", window.size(),
                "medianScore", medianScore);
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

    private double numericValue(Map<String, Object> row, String... keys) {
        for (String key : keys) {
            Object value = row.get(key);
            if (value instanceof Number number) {
                return number.doubleValue();
            }
        }
        return Double.POSITIVE_INFINITY;
    }
}
