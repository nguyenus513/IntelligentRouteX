package com.routechain.v2.decision;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class TileFeatureEncoder {

    List<Map<String, Object>> encode(List<Map<String, Object>> selectedTiles, List<Map<String, Object>> rows) {
        return selectedTiles.stream()
                .map(tile -> {
                    LinkedHashMap<String, Object> encoded = new LinkedHashMap<>(tile);
                    encoded.put("majorRoadRatio", average(rows, "majorRoadRatio"));
                    encoded.put("minorRoadRatio", average(rows, "minorRoadRatio"));
                    encoded.put("intersectionDensity", average(rows, "turnCount"));
                    encoded.put("trafficLevel", average(rows, "congestionScore"));
                    encoded.put("weatherRisk", average(rows, "weatherRisk", "weatherSensitivity"));
                    encoded.put("hotspotScore", average(rows, "score"));
                    encoded.put("merchantDensity", average(rows, "orderCount"));
                    encoded.put("avgExpectedSpeedMps", averageSpeed(rows));
                    encoded.put("turnComplexity", average(rows, "turnCount"));
                    encoded.put("corridorOverlapRatio", average(rows, "corridorOverlapRatio"));
                    return Map.copyOf(encoded);
                })
                .toList();
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
