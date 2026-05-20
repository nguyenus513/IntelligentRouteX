package com.routechain.v2.mladaptive;

import com.routechain.v2.hybrid.CandidateSource;
import com.routechain.v2.hybrid.SolutionSeedCandidate;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class AdaptiveSeedPolicy {
    private static final double ADAPTIVE_WEIGHT = 0.05;

    public Selection select(List<SolutionSeedCandidate> seeds, AdaptiveLearningState state) {
        Map<String, Double> scores = new LinkedHashMap<>();
        if (seeds == null || seeds.isEmpty()) {
            return new Selection(null, scores, "no-seeds");
        }
        for (SolutionSeedCandidate seed : seeds) {
            scores.put(seed.source().name(), score(seed, state));
        }
        SolutionSeedCandidate selected = seeds.stream()
                .filter(SolutionSeedCandidate::hardFeasible)
                .min(Comparator.comparingLong(SolutionSeedCandidate::lateOrderCount)
                        .thenComparingDouble(SolutionSeedCandidate::totalDistanceKm)
                        .thenComparing(seed -> -state.seedReward(seed.source())))
                .orElse(seeds.getFirst());
        return new Selection(selected.source(), scores, "hard-objective-first-adaptive-tiebreak");
    }

    private double score(SolutionSeedCandidate seed, AdaptiveLearningState state) {
        double coverageScore = seed.coverageRate() * 1000.0;
        double latePenalty = seed.lateOrderCount() * 200.0;
        double distanceCost = seed.totalDistanceKm();
        return round(coverageScore - latePenalty - distanceCost + (state.seedReward(seed.source()) * ADAPTIVE_WEIGHT));
    }

    private static double round(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }

    public record Selection(CandidateSource selectedBaseSeed, Map<String, Double> seedScores, String selectionReason) {
    }
}
