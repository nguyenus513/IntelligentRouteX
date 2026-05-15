package com.routechain.v2.routing;

import java.util.List;
import java.util.Map;

public record DistanceDurationMatrixSnapshot(
        String datasetId,
        String scenarioHash,
        String matrixProvider,
        String routingMode,
        List<String> nodeIds,
        Map<String, Integer> nodeIndex,
        Map<String, Integer> coordinateIndex,
        double[][] distanceKm,
        double[][] durationMinutes,
        boolean fallbackApplied,
        boolean cacheHit,
        long buildMs) {
}
