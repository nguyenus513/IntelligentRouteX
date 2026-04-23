package com.routechain.v2.integration;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

public record ForecastResponse(
        String schemaVersion,
        String traceId,
        String sourceModel,
        @JsonProperty("modelVersion")
        String modelVersion,
        @JsonProperty("artifactDigest")
        String artifactDigest,
        @JsonProperty("latencyMs")
        long latencyMs,
        @JsonProperty("fallbackUsed")
        boolean fallbackUsed,
        @JsonProperty("device")
        String device,
        @JsonProperty("dtype")
        String dtype,
        @JsonProperty("gpuMemoryAllocatedMb")
        long gpuMemoryAllocatedMb,
        @JsonProperty("batchSize")
        int batchSize,
        @JsonProperty("compileMode")
        String compileMode,
        @JsonProperty("modelLoaded")
        boolean modelLoaded,
        @JsonProperty("warmupDone")
        boolean warmupDone,
        ForecastPayload payload) {

    public record ForecastPayload(
            @JsonProperty("horizonMinutes")
            int horizonMinutes,
            @JsonProperty("shiftProbability")
            Double shiftProbability,
            @JsonProperty("burstProbability")
            Double burstProbability,
            Map<String, Double> quantiles,
            double confidence,
            @JsonProperty("sourceAgeMs")
            long sourceAgeMs) {
    }
}
