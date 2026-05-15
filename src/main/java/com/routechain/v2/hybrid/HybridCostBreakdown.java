package com.routechain.v2.hybrid;

public record HybridCostBreakdown(
        double distanceCost,
        double latenessCost,
        double loadPenalty,
        double shapePenalty,
        double riskPenalty,
        double mlUtility,
        double finalScore) {
}
