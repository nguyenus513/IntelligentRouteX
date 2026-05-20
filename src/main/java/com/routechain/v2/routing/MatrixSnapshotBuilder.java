package com.routechain.v2.routing;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class MatrixSnapshotBuilder {
    private static final Map<String, DistanceDurationMatrixSnapshot> CACHE = new ConcurrentHashMap<>();

    public DistanceDurationMatrixSnapshot build(String datasetId,
                                                String scenarioHash,
                                                String routingMode,
                                                List<MatrixNode> nodes) {
        List<MatrixNode> uniqueNodes = uniqueNodes(nodes);
        String provider = "synthetic-local-matrix";
        String cacheKey = datasetId + "|" + scenarioHash + "|" + routingMode + "|" + coordinateHash(uniqueNodes);
        DistanceDurationMatrixSnapshot cached = CACHE.get(cacheKey);
        if (cached != null) {
            return copyWithCacheHit(cached, true, 0L);
        }
        long started = System.nanoTime();
        int size = uniqueNodes.size();
        double[][] distances = new double[size][size];
        double[][] durations = new double[size][size];
        List<String> nodeIds = new ArrayList<>(size);
        Map<String, Integer> nodeIndex = new LinkedHashMap<>();
        Map<String, Integer> coordinateIndex = new LinkedHashMap<>();
        for (int index = 0; index < size; index++) {
            MatrixNode node = uniqueNodes.get(index);
            nodeIds.add(node.nodeId());
            nodeIndex.put(node.nodeId(), index);
            coordinateIndex.putIfAbsent(coordinateKey(node.latitude(), node.longitude()), index);
        }
        for (int from = 0; from < size; from++) {
            MatrixNode fromNode = uniqueNodes.get(from);
            for (int to = 0; to < size; to++) {
                MatrixNode toNode = uniqueNodes.get(to);
                double km = round(haversineKm(fromNode.latitude(), fromNode.longitude(), toNode.latitude(), toNode.longitude()));
                distances[from][to] = km;
                durations[from][to] = km / 22.0 * 60.0;
            }
        }
        DistanceDurationMatrixSnapshot snapshot = new DistanceDurationMatrixSnapshot(
                datasetId,
                scenarioHash,
                provider,
                routingMode,
                List.copyOf(nodeIds),
                Map.copyOf(nodeIndex),
                Map.copyOf(coordinateIndex),
                distances,
                durations,
                true,
                false,
                elapsedMs(started));
        CACHE.put(cacheKey, snapshot);
        return snapshot;
    }

    public DistanceDurationMatrixSnapshot buildWithOsrmTable(String datasetId,
                                                             String scenarioHash,
                                                             String routingMode,
                                                             List<MatrixNode> nodes,
                                                             OsrmTableClient osrmTableClient) {
        if (osrmTableClient == null) {
            return build(datasetId, scenarioHash, routingMode, nodes);
        }
        List<MatrixNode> uniqueNodes = uniqueNodes(nodes);
        String provider = osrmTableClient.providerId();
        String cacheKey = datasetId + "|" + scenarioHash + "|" + routingMode + "|" + provider + "|" + coordinateHash(uniqueNodes);
        DistanceDurationMatrixSnapshot cached = CACHE.get(cacheKey);
        if (cached != null) {
            return copyWithCacheHit(cached, true, 0L);
        }
        long started = System.nanoTime();
        List<RouteStop> stops = uniqueNodes.stream()
                .map(node -> new RouteStop(node.nodeId(), node.latitude(), node.longitude(), "MATRIX", "benchmark", null))
                .toList();
        DurationMatrix matrix = osrmTableClient.fetchMatrix(stops, stops);
        if (!matrix.degradeReasons().isEmpty() || !matrix.completeDurations() || matrix.nullDistanceCount() > 0) {
            return build(datasetId, scenarioHash, routingMode, uniqueNodes);
        }
        int size = uniqueNodes.size();
        double[][] distances = new double[size][size];
        double[][] durations = new double[size][size];
        List<String> nodeIds = new ArrayList<>(size);
        Map<String, Integer> nodeIndex = new LinkedHashMap<>();
        Map<String, Integer> coordinateIndex = new LinkedHashMap<>();
        for (int index = 0; index < size; index++) {
            MatrixNode node = uniqueNodes.get(index);
            nodeIds.add(node.nodeId());
            nodeIndex.put(node.nodeId(), index);
            coordinateIndex.putIfAbsent(coordinateKey(node.latitude(), node.longitude()), index);
        }
        for (int from = 0; from < size; from++) {
            for (int to = 0; to < size; to++) {
                Double meters = matrix.distanceMeters(from, to);
                Double seconds = matrix.durationSeconds(from, to);
                distances[from][to] = round((meters == null ? 0.0 : meters) / 1000.0);
                durations[from][to] = round((seconds == null ? 0.0 : seconds) / 60.0);
            }
        }
        DistanceDurationMatrixSnapshot snapshot = new DistanceDurationMatrixSnapshot(
                datasetId,
                scenarioHash,
                provider,
                routingMode,
                List.copyOf(nodeIds),
                Map.copyOf(nodeIndex),
                Map.copyOf(coordinateIndex),
                distances,
                durations,
                false,
                false,
                elapsedMs(started));
        CACHE.put(cacheKey, snapshot);
        return snapshot;
    }

    public static String coordinateKey(double lat, double lng) {
        return "%.6f,%.6f".formatted(lat, lng);
    }

    private static List<MatrixNode> uniqueNodes(List<MatrixNode> nodes) {
        Map<String, MatrixNode> byCoordinate = new LinkedHashMap<>();
        for (MatrixNode node : nodes == null ? List.<MatrixNode>of() : nodes) {
            byCoordinate.putIfAbsent(coordinateKey(node.latitude(), node.longitude()), node);
        }
        return List.copyOf(byCoordinate.values());
    }

    private static DistanceDurationMatrixSnapshot copyWithCacheHit(DistanceDurationMatrixSnapshot snapshot, boolean cacheHit, long buildMs) {
        return new DistanceDurationMatrixSnapshot(
                snapshot.datasetId(),
                snapshot.scenarioHash(),
                snapshot.matrixProvider(),
                snapshot.routingMode(),
                snapshot.nodeIds(),
                snapshot.nodeIndex(),
                snapshot.coordinateIndex(),
                snapshot.distanceKm(),
                snapshot.durationMinutes(),
                snapshot.fallbackApplied(),
                cacheHit,
                buildMs);
    }

    private static double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double radius = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private static double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private static long elapsedMs(long startedNanos) {
        return Math.max(0L, java.time.Duration.ofNanos(System.nanoTime() - startedNanos).toMillis());
    }

    private static String coordinateHash(List<MatrixNode> nodes) {
        return Integer.toHexString(nodes.stream()
                .map(node -> coordinateKey(node.latitude(), node.longitude()))
                .sorted()
                .toList()
                .hashCode()).toUpperCase();
    }

    public record MatrixNode(String nodeId, double latitude, double longitude) {
    }
}
