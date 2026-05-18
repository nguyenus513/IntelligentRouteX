package com.routechain.v2.seedimprovement;

import com.routechain.v2.hybrid.CandidateSource;

public record SeedImprovementAttribution(
        CandidateSource baseBestSeedSource,
        double baseBestSeedKm,
        int baseBestSeedAssigned,
        long baseBestSeedLate,
        CandidateSource finalSeedSource,
        double finalKm,
        int finalAssigned,
        long finalLate,
        double distanceGainOverBestSeedKm,
        boolean improvedBestSeed,
        SeedImprovementVerdict verdict) {
}
