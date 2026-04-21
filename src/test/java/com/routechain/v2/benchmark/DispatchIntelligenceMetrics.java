package com.routechain.v2.benchmark;

import com.routechain.v2.SchemaVersioned;

public record DispatchIntelligenceMetrics(
        String schemaVersion,
        double contextEfficiency,
        double stageCoherence,
        double fallbackRecoveryQuality,
        double adaptationQuality,
        double decisionConsistencyVariance,
        int llmRequestCount) implements SchemaVersioned {

    public static DispatchIntelligenceMetrics empty() {
        return new DispatchIntelligenceMetrics(
                "dispatch-intelligence-metrics/v1",
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0);
    }
}
