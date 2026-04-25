package com.routechain.v2.routing;

import java.util.List;

public record DurationMatrix(
        String schemaVersion,
        String provider,
        List<RouteStop> sourceStops,
        List<RouteStop> destinationStops,
        List<MatrixPoint> sources,
        List<MatrixPoint> destinations,
        List<List<Double>> durationsSeconds,
        List<List<Double>> distancesMeters,
        int nullDurationCount,
        int nullDistanceCount,
        long latencyMs,
        List<String> degradeReasons) {

    public DurationMatrix {
        sourceStops = sourceStops == null ? List.of() : List.copyOf(sourceStops);
        destinationStops = destinationStops == null ? List.of() : List.copyOf(destinationStops);
        sources = sources == null ? List.of() : List.copyOf(sources);
        destinations = destinations == null ? List.of() : List.copyOf(destinations);
        durationsSeconds = immutableRows(durationsSeconds);
        distancesMeters = immutableRows(distancesMeters);
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }

    public Double durationSeconds(int sourceIndex, int destinationIndex) {
        return valueAt(durationsSeconds, sourceIndex, destinationIndex);
    }

    public Double distanceMeters(int sourceIndex, int destinationIndex) {
        return valueAt(distancesMeters, sourceIndex, destinationIndex);
    }

    public boolean completeDurations() {
        return nullDurationCount == 0;
    }

    private static List<List<Double>> immutableRows(List<List<Double>> rows) {
        if (rows == null) {
            return List.of();
        }
        return rows.stream()
                .map(row -> row == null ? List.<Double>of() : java.util.Collections.unmodifiableList(new java.util.ArrayList<>(row)))
                .toList();
    }

    private static Double valueAt(List<List<Double>> rows, int sourceIndex, int destinationIndex) {
        if (sourceIndex < 0 || sourceIndex >= rows.size()) {
            return null;
        }
        List<Double> row = rows.get(sourceIndex);
        if (destinationIndex < 0 || destinationIndex >= row.size()) {
            return null;
        }
        return row.get(destinationIndex);
    }
}
