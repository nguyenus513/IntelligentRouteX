package com.routechain.v2.integration;

import java.util.ArrayList;
import java.util.List;

public final class MlWorkerAuditSupport {
    private MlWorkerAuditSupport() {
    }

    public static boolean auditPresent(MlWorkerMetadata metadata) {
        return missingFields(metadata).isEmpty();
    }

    public static String auditSource(MlWorkerMetadata metadata) {
        if (metadata == null) {
            return "missing";
        }
        boolean hasAnySignal = !(blankToEmpty(metadata.sourceModel()).isBlank()
                && blankToEmpty(metadata.modelVersion()).isBlank()
                && blankToEmpty(metadata.artifactDigest()).isBlank()
                && blankToEmpty(metadata.device()).isBlank()
                && blankToEmpty(metadata.dtype()).isBlank()
                && blankToEmpty(metadata.compileMode()).isBlank()
                && metadata.gpuMemoryAllocatedMb() <= 0L
                && metadata.batchSize() <= 0
                && !metadata.modelLoaded()
                && !metadata.warmupDone());
        return hasAnySignal ? "ready-state" : "missing";
    }

    public static List<String> missingFields(MlWorkerMetadata metadata) {
        if (metadata == null) {
            return List.of(
                    "device",
                    "dtype",
                    "batchSize",
                    "compileMode",
                    "modelLoaded",
                    "warmupDone");
        }
        List<String> missing = new ArrayList<>();
        if (blankToEmpty(metadata.device()).isBlank()) {
            missing.add("device");
        }
        if (blankToEmpty(metadata.dtype()).isBlank()) {
            missing.add("dtype");
        }
        if (metadata.batchSize() <= 0) {
            missing.add("batchSize");
        }
        if (blankToEmpty(metadata.compileMode()).isBlank()) {
            missing.add("compileMode");
        }
        if (!metadata.modelLoaded()) {
            missing.add("modelLoaded");
        }
        if (!metadata.warmupDone()) {
            missing.add("warmupDone");
        }
        if (!blankToEmpty(metadata.device()).isBlank()
                && metadata.device().toLowerCase(java.util.Locale.ROOT).startsWith("cuda")
                && metadata.gpuMemoryAllocatedMb() <= 0L) {
            missing.add("gpuMemoryAllocatedMb");
        }
        return List.copyOf(missing);
    }

    private static String blankToEmpty(String value) {
        return value == null ? "" : value;
    }
}
