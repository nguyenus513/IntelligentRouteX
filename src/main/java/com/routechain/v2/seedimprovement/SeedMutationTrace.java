package com.routechain.v2.seedimprovement;

public record SeedMutationTrace(
        String mutationId,
        String operator,
        boolean accepted,
        String verdict,
        double gainKm,
        PdValidationResult validation) {
}
