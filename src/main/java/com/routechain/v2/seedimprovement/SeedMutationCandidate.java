package com.routechain.v2.seedimprovement;

public record SeedMutationCandidate(
        String mutationId,
        String operator,
        PdSeedState candidateSeed,
        double oldKm,
        double newKm,
        double gainKm) {
}
