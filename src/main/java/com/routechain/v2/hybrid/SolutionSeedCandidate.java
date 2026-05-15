package com.routechain.v2.hybrid;

import java.util.List;

public record SolutionSeedCandidate(
        String solutionSeedId,
        CandidateSource source,
        List<SolutionSeedRoute> routes,
        double coverageRate,
        double totalDistanceKm,
        long lateOrderCount,
        List<DriverSeedLoad> driverLoadSummary,
        boolean hardFeasible,
        String hardInvalidReason,
        List<String> softPenaltyReasons,
        HybridCostBreakdown costBreakdown) {

    public SolutionSeedCandidate {
        routes = routes == null ? List.of() : List.copyOf(routes);
        driverLoadSummary = driverLoadSummary == null ? List.of() : List.copyOf(driverLoadSummary);
        softPenaltyReasons = softPenaltyReasons == null ? List.of() : List.copyOf(softPenaltyReasons);
        hardInvalidReason = hardInvalidReason == null ? "" : hardInvalidReason;
    }
}
