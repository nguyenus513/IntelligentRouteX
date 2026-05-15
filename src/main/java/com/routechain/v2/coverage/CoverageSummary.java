package com.routechain.v2.coverage;

public record CoverageSummary(
        int inputOrderCount,
        int assignedOrderCount,
        int deferredOrderCount,
        int rejectedOrderCount,
        int uncoveredOrderCount,
        int duplicateAssignedOrderCount,
        int accountedOrderCount,
        boolean accountingInvariantPassed,
        double coverageRate,
        boolean staticFinalHasDeferred) {
}
