package com.routechain.v2.integration;

public record MlWorkerMetadata(
        String sourceModel,
        String modelVersion,
        String artifactDigest,
        long latencyMs,
        String device,
        String dtype,
        long gpuMemoryAllocatedMb,
        int batchSize,
        String compileMode,
        boolean modelLoaded,
        boolean warmupDone) {

    public MlWorkerMetadata(String sourceModel,
                            String modelVersion,
                            String artifactDigest,
                            long latencyMs) {
        this(sourceModel, modelVersion, artifactDigest, latencyMs, "", "", 0L, 0, "", false, false);
    }

    public static MlWorkerMetadata empty() {
        return new MlWorkerMetadata("", "", "", 0L);
    }

    public boolean hasDeviceAudit() {
        return MlWorkerAuditSupport.auditPresent(this);
    }

    public MlWorkerMetadata withLatency(long latencyMs) {
        return new MlWorkerMetadata(
                sourceModel,
                modelVersion,
                artifactDigest,
                latencyMs,
                device,
                dtype,
                gpuMemoryAllocatedMb,
                batchSize,
                compileMode,
                modelLoaded,
                warmupDone);
    }
}
