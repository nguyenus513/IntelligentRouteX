package com.routechain.v2.hybrid;

import java.util.Optional;

public final class BaselineDominanceGuard {
    public BaselineDominanceResult evaluate(SolutionSeedCandidate finalSolution, EliteSolutionArchive archive) {
        Optional<SolutionSeedCandidate> bestSeed = archive == null ? Optional.empty() : archive.best();
        if (bestSeed.isEmpty()) {
            return new BaselineDominanceResult(true, null, 0.0, 0.0, 0.0, "no-feasible-seed");
        }
        if (finalSolution == null || !finalSolution.hardFeasible()) {
            SolutionSeedCandidate seed = bestSeed.get();
            return new BaselineDominanceResult(false, seed.source(), seed.totalDistanceKm(), 0.0, Double.NEGATIVE_INFINITY, "final-solution-infeasible");
        }
        SolutionSeedCandidate seed = bestSeed.get();
        double finalScore = finalSolution.costBreakdown().finalScore();
        double seedScore = seed.costBreakdown().finalScore();
        boolean passed = LexicographicSolutionComparator.SLA_STRICT.compare(finalSolution, seed) >= 0;
        double distanceDelta = finalSolution.totalDistanceKm() - seed.totalDistanceKm();
        return new BaselineDominanceResult(passed, seed.source(), seed.totalDistanceKm(), distanceDelta, finalScore - seedScore, passed ? "final-dominates-best-seed-lexicographic" : "rollback-to-best-seed-required-lexicographic");
    }
}
