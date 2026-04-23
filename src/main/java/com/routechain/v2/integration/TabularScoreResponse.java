package com.routechain.v2.integration;

public record TabularScoreResponse(
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
        TabularScorePayload payload) {

    public record TabularScorePayload(
            double score,
            double uncertainty) {
    }
}
