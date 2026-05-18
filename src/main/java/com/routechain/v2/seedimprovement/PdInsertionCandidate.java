package com.routechain.v2.seedimprovement;

public record PdInsertionCandidate(
        PdSeedState seed,
        PdEvaluation evaluation,
        String orderId,
        String routeId,
        int pickupPosition,
        int dropoffPosition,
        int evaluatedCandidates,
        int feasibleCandidates) {
}
