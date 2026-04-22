package com.routechain.v2.decision;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class GeoTileSelector {

    List<Map<String, Object>> select(DecisionStageName stageName,
                                     List<Map<String, Object>> rows,
                                     Map<String, Object> dispatchContext) {
        return rows.stream()
                .limit(3)
                .map(row -> {
                    LinkedHashMap<String, Object> tile = new LinkedHashMap<>();
                    double lat = firstNumber(row, "bundleCentroidLat", "pickupLat", "driverLat");
                    double lng = firstNumber(row, "bundleCentroidLng", "pickupLng", "driverLng");
                    double pointCoverage = hasCoordinate(row, "pickupLat", "pickupLng") ? 1.0 : 0.5;
                    double corridorOverlap = safeNumber(row.get("corridorOverlapRatio"));
                    double trafficRelevance = safeNumber(row.get("congestionScore"));
                    double hotspotDensity = safeNumber(row.get("score"));
                    double weatherRisk = safeNumber(row.get("weatherRisk"));
                    tile.put("tileId", tileId(lat, lng));
                    tile.put("zoomLevel", 15);
                    tile.put("priorityScore", clamp(0.30 + (pointCoverage * 0.20) + (corridorOverlap * 0.25) + (trafficRelevance * 0.15) + (hotspotDensity * 0.10)));
                    tile.put("selectionReasonCodes", List.of(stageName.wireName(), String.valueOf(dispatchContext.getOrDefault("trafficClass", "unknown"))));
                    tile.put("pointCoverage", pointCoverage);
                    tile.put("corridorOverlap", corridorOverlap);
                    tile.put("trafficRelevance", trafficRelevance);
                    tile.put("hotspotDensity", hotspotDensity);
                    tile.put("weatherRisk", weatherRisk);
                    tile.put("sourceProvenance", Map.of(
                            "traffic", dispatchContext.getOrDefault("trafficClass", "unknown"),
                            "weather", dispatchContext.getOrDefault("weatherClass", "unknown"),
                            "kind", "estimated"));
                    return Map.copyOf(tile);
                })
                .toList();
    }

    private boolean hasCoordinate(Map<String, Object> row, String latKey, String lngKey) {
        return row.get(latKey) instanceof Number && row.get(lngKey) instanceof Number;
    }

    private String tileId(double lat, double lng) {
        return "tile:%d:%d".formatted(Math.round(lat * 100.0), Math.round(lng * 100.0));
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

    private double safeNumber(Object value) {
        return value instanceof Number number ? number.doubleValue() : 0.0;
    }

    private double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }
}
