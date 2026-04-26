package com.routechain.v2.integration;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record WorkerVersionResponse(
        String schemaVersion,
        String worker,
        String model,
        @JsonProperty("modelVersion")
        String modelVersion,
        @JsonProperty("artifactDigest")
        String artifactDigest,
        @JsonProperty("compatibilityContractVersion")
        String compatibilityContractVersion,
        @JsonProperty("minSupportedJavaContractVersion")
        String minSupportedJavaContractVersion,
        @JsonProperty("loadedFromLocal")
        Boolean loadedFromLocal,
        @JsonProperty("localArtifactPath")
        String localArtifactPath,
        @JsonProperty("materializationMode")
        String materializationMode,
        @JsonProperty("loadedModelFingerprint")
        String loadedModelFingerprint,
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
        @JsonProperty("runtimeMode")
        String runtimeMode) {
}
