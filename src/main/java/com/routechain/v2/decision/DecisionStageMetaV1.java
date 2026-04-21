package com.routechain.v2.decision;

import com.routechain.v2.SchemaVersioned;

import java.util.Map;

public record DecisionStageMetaV1(
        String schemaVersion,
        long latencyMs,
        double confidence,
        boolean fallbackUsed,
        String fallbackReason,
        boolean validationPassed,
        String appliedSource,
        String requestedEffort,
        String appliedEffort,
        Map<String, Object> tokenUsage,
        int retryCount,
        String rawResponseHash,
        String authorityMode,
        java.util.List<String> authoritativeStageSet,
        java.util.List<String> decisionQualityFlags,
        String contextProfile,
        java.util.List<String> overlaySet,
        boolean contextCompressionApplied,
        String effortSelectionReason) implements SchemaVersioned {

    public DecisionStageMetaV1 {
        tokenUsage = tokenUsage == null ? Map.of() : Map.copyOf(tokenUsage);
        authoritativeStageSet = authoritativeStageSet == null ? java.util.List.of() : java.util.List.copyOf(authoritativeStageSet);
        decisionQualityFlags = decisionQualityFlags == null ? java.util.List.of() : java.util.List.copyOf(decisionQualityFlags);
        overlaySet = overlaySet == null ? java.util.List.of() : java.util.List.copyOf(overlaySet);
    }

    public static DecisionStageMetaV1 legacy(long latencyMs) {
        return new DecisionStageMetaV1(
                "decision-stage-meta/v1",
                latencyMs,
                1.0,
                false,
                null,
                true,
                "legacy",
                null,
                null,
                Map.of(),
                0,
                null,
                "legacy",
                java.util.List.of(),
                java.util.List.of(),
                "legacy-static",
                java.util.List.of(),
                false,
                "legacy-default");
    }
}
