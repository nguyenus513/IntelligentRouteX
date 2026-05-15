package com.routechain.v2.hybrid;

public record BaselineDominanceResult(
        boolean passed,
        CandidateSource bestSeedSource,
        double bestSeedDistanceKm,
        double finalImprovementOverBestSeedKm,
        double finalObjectiveDelta,
        String reason) {
}
