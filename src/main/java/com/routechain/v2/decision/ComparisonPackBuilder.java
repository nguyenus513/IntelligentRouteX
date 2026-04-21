package com.routechain.v2.decision;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class ComparisonPackBuilder {

    Map<String, Object> build(Map<String, Object> candidateSet, Map<String, Object> referenceFrame) {
        List<Map<String, Object>> window = rows(candidateSet.get("window"));
        if (window.isEmpty()) {
            return Map.of("items", List.of(), "windowSize", 0);
        }
        double bestEta = bestMetric(window, "projectedPickupEtaMinutes", "pickupEtaMinutes", "expectedValue");
        double bestCost = bestMetric(window, "routeCost", "selectionScore", "score");
        double bestCongestion = bestMetric(window, "congestionScore");
        double bestDriverDistance = bestMetric(window, "effectiveDistanceMeters", "driverToFirstPickupEtaSeconds", "pickupEtaMinutes");
        double baselineScore = baselineScore(referenceFrame);
        List<Map<String, Object>> items = window.stream()
                .map(row -> comparisonRow(row, window, bestEta, bestCost, bestCongestion, bestDriverDistance, baselineScore))
                .toList();
        return Map.of(
                "windowSize", window.size(),
                "items", items);
    }

    Map<String, Object> augmentForPasses(Map<String, Object> comparisonPack,
                                         Map<String, Object> proposeOutput,
                                         Map<String, Object> critiqueOutput) {
        LinkedHashMap<String, Object> augmented = new LinkedHashMap<>(comparisonPack == null ? Map.of() : comparisonPack);
        augmented.put("llmPassFeedback", Map.of(
                "proposeSelectedIds", selectedIds(proposeOutput),
                "critiqueSelectedIds", selectedIds(critiqueOutput),
                "critiqueReasonCodes", reasonCodes(critiqueOutput)));
        return Map.copyOf(augmented);
    }

    private Map<String, Object> comparisonRow(Map<String, Object> row,
                                              List<Map<String, Object>> window,
                                              double bestEta,
                                              double bestCost,
                                              double bestCongestion,
                                              double bestDriverDistance,
                                              double baselineScore) {
        String id = id(row);
        double score = numericValue(row, "routeValue", "selectionScore", "score", "robustUtility");
        List<String> dominatesIds = window.stream()
                .filter(other -> !id(other).equals(id))
                .filter(other -> score > numericValue(other, "routeValue", "selectionScore", "score", "robustUtility"))
                .map(this::id)
                .toList();
        List<String> dominatedByIds = window.stream()
                .filter(other -> !id(other).equals(id))
                .filter(other -> score < numericValue(other, "routeValue", "selectionScore", "score", "robustUtility"))
                .map(this::id)
                .toList();
        return Map.of(
                "id", id,
                "deltaToBestEta", delta(row, bestEta, "projectedPickupEtaMinutes", "pickupEtaMinutes", "expectedValue"),
                "deltaToBestCost", delta(row, bestCost, "routeCost", "selectionScore", "score"),
                "deltaToBestCongestion", delta(row, bestCongestion, "congestionScore"),
                "deltaToBestDriverDistance", delta(row, bestDriverDistance, "effectiveDistanceMeters", "driverToFirstPickupEtaSeconds", "pickupEtaMinutes"),
                "deltaToBaseline", Double.isFinite(score) && Double.isFinite(baselineScore) ? score - baselineScore : 0.0,
                "dominatesIds", dominatesIds,
                "dominatedByIds", dominatedByIds,
                "regretEstimate", Math.max(0.0, bestOf(window) - safeScore(score)));
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

    private double bestMetric(List<Map<String, Object>> rows, String... keys) {
        return rows.stream()
                .mapToDouble(row -> numericValue(row, keys))
                .filter(Double::isFinite)
                .min()
                .orElse(0.0);
    }

    private double bestOf(List<Map<String, Object>> rows) {
        return rows.stream()
                .mapToDouble(row -> safeScore(numericValue(row, "routeValue", "selectionScore", "score", "robustUtility")))
                .max()
                .orElse(0.0);
    }

    private double baselineScore(Map<String, Object> referenceFrame) {
        if (referenceFrame == null) {
            return 0.0;
        }
        Object baseline = referenceFrame.get("heuristicBaseline");
        if (!(baseline instanceof Map<?, ?> map)) {
            return 0.0;
        }
        Object score = map.get("score");
        return score instanceof Number number ? number.doubleValue() : 0.0;
    }

    private double delta(Map<String, Object> row, double baseline, String... keys) {
        double value = numericValue(row, keys);
        if (!Double.isFinite(value) || !Double.isFinite(baseline)) {
            return 0.0;
        }
        return value - baseline;
    }

    private List<String> selectedIds(Map<String, Object> output) {
        Object value = output == null ? null : output.get("selectedIds");
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return list.stream().map(String::valueOf).toList();
    }

    private List<String> reasonCodes(Map<String, Object> output) {
        if (!(output instanceof Map<?, ?>)) {
            return List.of();
        }
        Object assessments = output.get("assessments");
        if (!(assessments instanceof Map<?, ?> assessmentMap)) {
            return List.of();
        }
        Object value = assessmentMap.get("reasonCodes");
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return list.stream().map(String::valueOf).toList();
    }

    private String id(Map<String, Object> row) {
        return String.valueOf(row.getOrDefault("id", row.getOrDefault("proposalId", row.getOrDefault("driverId", row.getOrDefault("bundleId", "")))));
    }

    private double numericValue(Map<String, Object> row, String... keys) {
        for (String key : keys) {
            Object value = row.get(key);
            if (value instanceof Number number) {
                return number.doubleValue();
            }
        }
        return Double.NaN;
    }

    private double safeScore(double value) {
        return Double.isFinite(value) ? value : 0.0;
    }
}
