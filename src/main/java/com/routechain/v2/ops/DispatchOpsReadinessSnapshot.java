package com.routechain.v2.ops;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public record DispatchOpsReadinessSnapshot(
        String schemaVersion,
        boolean dispatchEnabled,
        boolean mlEnabled,
        boolean sidecarRequired,
        String storageMode,
        String feedbackBaseDir,
        boolean warmStartEnabled,
        boolean hotStartEnabled,
        boolean loadLatestSnapshotOnBoot,
        String bootMode,
        boolean latestSnapshotLoaded,
        String latestSnapshotId,
        String latestSnapshotTraceId,
        List<String> warmStartDegradeReasons,
        List<DispatchOpsWorkerReadiness> workers,
        List<DispatchOpsLiveSourceStatus> liveSources) {

    public Map<String, Object> toMap() {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("schemaVersion", schemaVersion);
        details.put("dispatchEnabled", dispatchEnabled);
        details.put("mlEnabled", mlEnabled);
        details.put("sidecarRequired", sidecarRequired);
        details.put("storageMode", storageMode);
        details.put("feedbackBaseDir", feedbackBaseDir);
        details.put("warmStartEnabled", warmStartEnabled);
        details.put("hotStartEnabled", hotStartEnabled);
        details.put("loadLatestSnapshotOnBoot", loadLatestSnapshotOnBoot);
        details.put("bootMode", bootMode);
        details.put("latestSnapshotLoaded", latestSnapshotLoaded);
        details.put("latestSnapshotId", latestSnapshotId);
        details.put("latestSnapshotTraceId", latestSnapshotTraceId);
        details.put("warmStartDegradeReasons", warmStartDegradeReasons);
        details.put("workers", workers.stream().map(DispatchOpsWorkerReadiness::toMap).toList());
        details.put("liveSources", liveSources.stream().map(DispatchOpsLiveSourceStatus::toMap).toList());
        return details;
    }

    public record DispatchOpsWorkerReadiness(
            String workerName,
            boolean enabled,
            boolean ready,
            String reason,
            String sourceModel,
            String modelVersion,
            String artifactDigest,
            String loadedModelFingerprint,
            String device,
            String dtype,
            long gpuMemoryAllocatedMb,
            int batchSize,
            String compileMode,
            boolean modelLoaded,
            boolean warmupDone) {

        public Map<String, Object> toMap() {
            Map<String, Object> details = new LinkedHashMap<>();
            details.put("workerName", workerName);
            details.put("enabled", enabled);
            details.put("ready", ready);
            details.put("reason", reason);
            details.put("sourceModel", sourceModel);
            details.put("modelVersion", modelVersion);
            details.put("artifactDigest", artifactDigest);
            details.put("loadedModelFingerprint", loadedModelFingerprint);
            details.put("device", device);
            details.put("dtype", dtype);
            details.put("gpuMemoryAllocatedMb", gpuMemoryAllocatedMb);
            details.put("batchSize", batchSize);
            details.put("compileMode", compileMode);
            details.put("modelLoaded", modelLoaded);
            details.put("warmupDone", warmupDone);
            return details;
        }
    }

    public record DispatchOpsLiveSourceStatus(
            String sourceName,
            boolean enabled,
            String observedMode,
            boolean apiKeyPresent) {

        public Map<String, Object> toMap() {
            Map<String, Object> details = new LinkedHashMap<>();
            details.put("sourceName", sourceName);
            details.put("enabled", enabled);
            details.put("observedMode", observedMode);
            if ("tomtom-traffic".equals(sourceName)) {
                details.put("apiKeyPresent", apiKeyPresent);
            }
            return details;
        }
    }
}
