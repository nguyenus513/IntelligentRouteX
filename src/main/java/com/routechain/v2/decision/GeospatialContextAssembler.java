package com.routechain.v2.decision;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class GeospatialContextAssembler {

    Map<String, Object> build(DecisionStageName stageName, Map<String, Object> candidateSet, Map<String, Object> dispatchContext) {
        List<Map<String, Object>> window = rows(candidateSet.get("window"));
        if (window.isEmpty()) {
            return Map.of("stageName", stageName.wireName(), "tileContextSummaries", List.of());
        }
        LinkedHashMap<String, Object> context = new LinkedHashMap<>();
        context.put("stageName", stageName.wireName());
        context.put("zoneId", dispatchContext.getOrDefault("zoneId", dispatchContext.getOrDefault("corridorSignature", "unknown-zone")));
        context.put("corridorId", dispatchContext.getOrDefault("corridorSignature", "unknown-corridor"));
        context.put("localDriverAreaSummary", firstWithKeys(window, "driverLat", "driverLng"));
        context.put("pickupDropClusterSummary", clusterSummary(window));
        context.put("corridorSummary", corridorSummary(window, dispatchContext));
        context.put("tileContextSummaries", tileSummaries(window));
        context.put("geospatialReferenceFrame", Map.of(
                "driverToFirstPickupEtaSeconds", min(window, "driverToFirstPickupEtaSeconds", "pickupEtaMinutes"),
                "effectiveDistanceMeters", min(window, "effectiveDistanceMeters"),
                "bundleCentroidLat", average(window, "bundleCentroidLat", "pickupLat"),
                "bundleCentroidLng", average(window, "bundleCentroidLng", "pickupLng")));
        return Map.copyOf(context);
    }

    private Map<String, Object> firstWithKeys(List<Map<String, Object>> rows, String... keys) {
        for (Map<String, Object> row : rows) {
            boolean present = true;
            LinkedHashMap<String, Object> values = new LinkedHashMap<>();
            for (String key : keys) {
                if (!row.containsKey(key)) {
                    present = false;
                    break;
                }
                values.put(key, row.get(key));
            }
            if (present) {
                values.put("id", id(row));
                return Map.copyOf(values);
            }
        }
        return Map.of();
    }

    private Map<String, Object> clusterSummary(List<Map<String, Object>> rows) {
        return Map.of(
                "pickupClusterRadiusMeters", average(rows, "pickupClusterRadiusMeters"),
                "dropClusterRadiusMeters", average(rows, "dropClusterRadiusMeters"),
                "pickupDropDirectionalConsistency", average(rows, "pickupDropDirectionalConsistency"),
                "windowCount", rows.size());
    }

    private Map<String, Object> corridorSummary(List<Map<String, Object>> rows, Map<String, Object> dispatchContext) {
        return Map.of(
                "corridorId", dispatchContext.getOrDefault("corridorSignature", "unknown-corridor"),
                "majorRoadRatio", average(rows, "majorRoadRatio"),
                "minorRoadRatio", average(rows, "minorRoadRatio"),
                "congestionScore", average(rows, "congestionScore"),
                "straightnessScore", average(rows, "straightnessScore"));
    }

    private List<Map<String, Object>> tileSummaries(List<Map<String, Object>> rows) {
        return rows.stream()
                .limit(3)
                .map(row -> {
                    LinkedHashMap<String, Object> summary = new LinkedHashMap<>();
                    summary.put("tileId", id(row));
                    summary.put("majorRoadRatio", safeNumber(row.get("majorRoadRatio")));
                    summary.put("minorRoadRatio", safeNumber(row.get("minorRoadRatio")));
                    summary.put("intersectionDensity", safeNumber(row.get("turnCount")));
                    summary.put("trafficLevel", safeNumber(row.get("congestionScore")));
                    summary.put("weatherRisk", safeNumber(row.get("weatherSensitivity")));
                    summary.put("merchantDensity", safeNumber(row.get("orderCount")));
                    summary.put("hotspotScore", safeNumber(row.get("score")));
                    summary.put("avgExpectedSpeedMps", speed(row));
                    summary.put("turnComplexity", safeNumber(row.get("turnCount")));
                    summary.put("corridorOverlapRatio", safeNumber(row.get("corridorOverlapRatio")));
                    return Map.copyOf(summary);
                })
                .toList();
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

    private double min(List<Map<String, Object>> rows, String... keys) {
        return rows.stream()
                .mapToDouble(row -> firstNumber(row, keys))
                .filter(Double::isFinite)
                .min()
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

    private double speed(Map<String, Object> row) {
        Object distance = row.get("distanceMeters");
        Object duration = row.get("travelTimeSeconds");
        if (distance instanceof Number distanceNumber && duration instanceof Number durationNumber && durationNumber.doubleValue() > 0.0) {
            return distanceNumber.doubleValue() / durationNumber.doubleValue();
        }
        return 0.0;
    }

    private double safeNumber(Object value) {
        return value instanceof Number number ? number.doubleValue() : 0.0;
    }

    private String id(Map<String, Object> row) {
        return String.valueOf(row.getOrDefault("id", row.getOrDefault("proposalId", row.getOrDefault("driverId", row.getOrDefault("bundleId", "")))));
    }
}
