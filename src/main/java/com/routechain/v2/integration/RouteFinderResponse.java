package com.routechain.v2.integration;

import java.util.List;

public record RouteFinderResponse(
        String schemaVersion,
        String traceId,
        String sourceModel,
        String modelVersion,
        String artifactDigest,
        long latencyMs,
        boolean fallbackUsed,
        String device,
        String dtype,
        long gpuMemoryAllocatedMb,
        int batchSize,
        String compileMode,
        boolean modelLoaded,
        boolean warmupDone,
        RouteFinderPayload payload) {

    public record RouteFinderPayload(
            List<RouteFinderRoutePayload> routes) {
    }

    public record RouteFinderRoutePayload(
            List<String> stopOrder,
            double projectedPickupEtaMinutes,
            double projectedCompletionEtaMinutes,
            double routeScore,
            List<String> traceReasons) {
    }
}
