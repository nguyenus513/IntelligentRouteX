package com.routechain.v2.benchmark;

import com.routechain.v2.SchemaVersioned;
import com.routechain.v2.repair.RepairOperatorStat;
import com.routechain.v2.repair.RepairTelemetry;

import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public record DispatchRepairTelemetryMetrics(
        String schemaVersion,
        String mode,
        boolean enabled,
        boolean timedOut,
        long runtimeMs,
        int candidateInputCount,
        int candidateOutputCount,
        int operatorsTried,
        int acceptedMoves,
        int rejectedMoves,
        double bestImprovementDelta,
        int frozenPrefixViolationCount,
        int foodDurationViolationCount,
        double freshnessImprovementDelta,
        double tailRiskImprovementDelta,
        Map<String, Integer> operatorCounts,
        List<String> rejectionReasons,
        List<String> degradeReasons) implements SchemaVersioned {

    public DispatchRepairTelemetryMetrics {
        mode = mode == null || mode.isBlank() ? "DISABLED_OR_EMPTY" : mode;
        operatorCounts = operatorCounts == null ? Map.of() : Map.copyOf(operatorCounts);
        rejectionReasons = rejectionReasons == null ? List.of() : List.copyOf(rejectionReasons);
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }

    public static DispatchRepairTelemetryMetrics empty() {
        return new DispatchRepairTelemetryMetrics(
                "dispatch-repair-telemetry-metrics/v1",
                "DISABLED_OR_EMPTY",
                false,
                false,
                0L,
                0,
                0,
                0,
                0,
                0,
                0.0,
                0,
                0,
                0.0,
                0.0,
                Map.of(),
                List.of(),
                List.of());
    }

    public static DispatchRepairTelemetryMetrics from(RepairTelemetry telemetry) {
        if (telemetry == null) {
            return empty();
        }
        boolean enabled = telemetry.candidateInputCount() > 0 || telemetry.operatorsTried() > 0;
        Map<String, Integer> operatorCounts = new TreeMap<>();
        for (RepairOperatorStat stat : telemetry.operatorStats()) {
            String name = stat.operatorName() == null || stat.operatorName().isBlank() ? "unknown" : stat.operatorName();
            operatorCounts.merge(name, Math.max(0, stat.triedCount()), Integer::sum);
        }
        return new DispatchRepairTelemetryMetrics(
                "dispatch-repair-telemetry-metrics/v1",
                enabled ? "BOUNDED_ALNS" : "DISABLED_OR_EMPTY",
                enabled,
                telemetry.timedOut(),
                Math.max(0L, telemetry.runtimeMs()),
                Math.max(0, telemetry.candidateInputCount()),
                Math.max(0, telemetry.candidateOutputCount()),
                Math.max(0, telemetry.operatorsTried()),
                Math.max(0, telemetry.acceptedMoves()),
                Math.max(0, telemetry.rejectedMoves()),
                telemetry.bestImprovementDelta(),
                telemetry.improvementSummary().frozenPrefixViolationCount(),
                telemetry.improvementSummary().foodDurationViolationCount(),
                telemetry.improvementSummary().freshnessImprovementDelta(),
                telemetry.improvementSummary().tailRiskImprovementDelta(),
                operatorCounts,
                telemetry.rejectionReasons(),
                telemetry.degradeReasons());
    }
}
