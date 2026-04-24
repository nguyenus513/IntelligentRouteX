package com.routechain.v2.benchmark;

import com.routechain.v2.SchemaVersioned;

public record DispatchQualityMetrics(
        String schemaVersion,
        int selectedProposalCount,
        int executedAssignmentCount,
        boolean conflictFreeAssignments,
        boolean executionValid,
        double bundleRate,
        double averageBundleSize,
        int selectedSingleOrderCount,
        int selectedBundleSize2Count,
        int selectedBundleSize3Count,
        int selectedBundleSize4Count,
        int selectedBundleSize5Count,
        int coveredOrderCount,
        int maxSelectedBundleSize,
        double routeFallbackRate,
        double averageProjectedPickupEtaMinutes,
        double averageProjectedCompletionEtaMinutes,
        double landingValueAverage,
        double robustUtilityAverage,
        double selectorObjectiveValue,
        double routeCostQuality,
        double driverEntryQuality,
        double burstRobustness,
        double dispatchRegretAverage,
        double courierUtilizationEstimate,
        double degradeRate,
        double workerFallbackRate,
        double liveSourceFallbackRate) implements SchemaVersioned {
}
