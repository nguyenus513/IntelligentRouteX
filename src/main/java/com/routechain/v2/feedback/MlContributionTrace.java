package com.routechain.v2.feedback;

import com.routechain.v2.MlStageMetadata;
import com.routechain.v2.SchemaVersioned;

public record MlContributionTrace(
        String schemaVersion,
        String stageName,
        String sourceModel,
        String modelVersion,
        String artifactDigest,
        long latencyMs,
        boolean applied,
        boolean fallbackUsed,
        String contributionMode,
        String fallbackReason) implements SchemaVersioned {

    public static MlContributionTrace from(MlStageMetadata metadata) {
        String contributionMode;
        String fallbackReason = "";
        if (metadata.fallbackUsed()) {
            contributionMode = "fallback";
            fallbackReason = "ml-worker-fallback-used";
        } else if (metadata.applied()) {
            contributionMode = "applied";
        } else {
            contributionMode = "observed";
        }
        return new MlContributionTrace(
                "ml-contribution-trace/v1",
                metadata.stageName(),
                metadata.sourceModel(),
                metadata.modelVersion(),
                metadata.artifactDigest(),
                metadata.latencyMs(),
                metadata.applied(),
                metadata.fallbackUsed(),
                contributionMode,
                fallbackReason);
    }
}
