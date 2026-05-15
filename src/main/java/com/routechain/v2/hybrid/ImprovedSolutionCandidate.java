package com.routechain.v2.hybrid;

public record ImprovedSolutionCandidate(
        SolutionSeedCandidate originalSeed,
        SolutionSeedCandidate improvedSeed,
        ImprovementTrace trace) {
}
