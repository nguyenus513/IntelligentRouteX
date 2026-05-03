package com.routechain.v2.benchmark;

import com.routechain.v2.selector.GlobalSelectorSummary;

import java.util.List;

public record DispatchSelectorTelemetryMetrics(
        String mode,
        int poolInputCount,
        int poolReducedCount,
        int poolRejectedCount,
        boolean timedOut,
        String fallbackLevel,
        boolean acceptanceGatePassed,
        List<String> acceptanceGateRejectedReasons,
        int selectorMaxPoolSize,
        boolean selectorPoolCapApplied,
        double selectorPoolCapObjectiveLoss) {

    public DispatchSelectorTelemetryMetrics {
        mode = mode == null ? "UNKNOWN" : mode;
        fallbackLevel = fallbackLevel == null ? "NONE" : fallbackLevel;
        acceptanceGateRejectedReasons = acceptanceGateRejectedReasons == null ? List.of() : List.copyOf(acceptanceGateRejectedReasons);
    }

    public static DispatchSelectorTelemetryMetrics empty() {
        return new DispatchSelectorTelemetryMetrics("NONE", 0, 0, 0, false, "NONE", true, List.of(), 0, false, 0.0);
    }

    public static DispatchSelectorTelemetryMetrics from(GlobalSelectorSummary summary) {
        if (summary == null) {
            return empty();
        }
        return new DispatchSelectorTelemetryMetrics(
                summary.solverMode().name(),
                summary.poolInputCount(),
                summary.poolReducedCount(),
                summary.poolRejectedCount(),
                summary.selectorTimedOut(),
                summary.selectorFallbackLevel(),
                summary.acceptanceGatePassed(),
                summary.acceptanceGateRejectedReasons(),
                summary.selectorMaxPoolSize(),
                summary.selectorPoolCapApplied(),
                summary.selectorPoolCapObjectiveLoss());
    }
}
