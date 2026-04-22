package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

final class GeoContextAssembler {
    private final GeoTileSelector tileSelector = new GeoTileSelector();
    private final TileFeatureEncoder tileFeatureEncoder = new TileFeatureEncoder();

    Map<String, Object> build(DecisionStageName stageName, List<Map<String, Object>> rows, Map<String, Object> dispatchContext) {
        List<Map<String, Object>> selectedTiles = tileSelector.select(stageName, rows, dispatchContext);
        List<Map<String, Object>> tileFeatures = tileFeatureEncoder.encode(selectedTiles, rows);
        return Map.of(
                "localDriverAreaSummary", firstWithKeys(rows, "driverLat", "driverLng"),
                "pickupDropClusterSummary", Map.of(
                        "pickupClusterRadiusMeters", average(rows, "pickupClusterRadiusMeters"),
                        "dropClusterRadiusMeters", average(rows, "dropClusterRadiusMeters"),
                        "routeSpreadMeters", average(rows, "routeSpreadMeters"),
                        "bundleCompactnessScore", average(rows, "bundleCompactnessScore")),
                "corridorSummary", Map.of(
                        "corridorId", dispatchContext.getOrDefault("corridorSignature", "unknown-corridor"),
                        "majorRoadRatio", average(rows, "majorRoadRatio"),
                        "minorRoadRatio", average(rows, "minorRoadRatio"),
                        "congestionScore", average(rows, "congestionScore"),
                        "avgExpectedSpeedMps", averageSpeed(rows)),
                "selectedTiles", selectedTiles,
                "tileContextSummaries", tileFeatures);
    }

    private Map<String, Object> firstWithKeys(List<Map<String, Object>> rows, String... keys) {
        for (Map<String, Object> row : rows) {
            boolean present = true;
            java.util.LinkedHashMap<String, Object> values = new java.util.LinkedHashMap<>();
            for (String key : keys) {
                if (!row.containsKey(key)) {
                    present = false;
                    break;
                }
                values.put(key, row.get(key));
            }
            if (present) {
                values.put("id", String.valueOf(row.getOrDefault("id", "")));
                return Map.copyOf(values);
            }
        }
        return Map.of();
    }

    private double average(List<Map<String, Object>> rows, String... keys) {
        return rows.stream()
                .mapToDouble(row -> firstNumber(row, keys))
                .average()
                .orElse(0.0);
    }

    private double averageSpeed(List<Map<String, Object>> rows) {
        return rows.stream()
                .mapToDouble(row -> {
                    double distance = firstNumber(row, "distanceMeters", "effectiveDistanceMeters");
                    double duration = firstNumber(row, "travelTimeSeconds", "driverToFirstPickupEtaSeconds");
                    return duration <= 0.0 ? 0.0 : distance / duration;
                })
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
        return 0.0;
    }
}
