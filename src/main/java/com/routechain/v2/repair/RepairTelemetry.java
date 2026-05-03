package com.routechain.v2.repair;

import java.util.List;

public record RepairTelemetry(
        String schemaVersion,
        int candidateInputCount,
        int candidateOutputCount,
        int operatorsTried,
        int acceptedMoves,
        int rejectedMoves,
        boolean timedOut,
        long runtimeMs,
        double bestImprovementDelta,
        List<RepairOperatorStat> operatorStats,
        List<String> rejectionReasons,
        List<String> degradeReasons,
        RepairImprovementSummary improvementSummary) {

    public RepairTelemetry {
        operatorStats = operatorStats == null ? List.of() : List.copyOf(operatorStats);
        rejectionReasons = rejectionReasons == null ? List.of() : List.copyOf(rejectionReasons);
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
        improvementSummary = improvementSummary == null ? RepairImprovementSummary.empty() : improvementSummary;
    }

    public static RepairTelemetry empty() {
        return new RepairTelemetry(
                "repair-telemetry/v1",
                0,
                0,
                0,
                0,
                0,
                false,
                0L,
                0.0,
                List.of(),
                List.of(),
                List.of("active-repair-no-input"),
                RepairImprovementSummary.empty());
    }
}
