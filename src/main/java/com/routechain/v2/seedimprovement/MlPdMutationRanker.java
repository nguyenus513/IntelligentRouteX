package com.routechain.v2.seedimprovement;

import java.util.Comparator;
import java.util.List;

public final class MlPdMutationRanker {
    public List<PdInsertionCandidate> rankInsertions(List<PdInsertionCandidate> candidates) {
        if (candidates == null) {
            return List.of();
        }
        return candidates.stream()
                .filter(candidate -> candidate != null && candidate.evaluation() != null && candidate.evaluation().valid())
                .sorted(Comparator.comparingDouble(this::score).reversed())
                .toList();
    }

    private double score(PdInsertionCandidate candidate) {
        PdEvaluation evaluation = candidate.evaluation();
        double routeBias = Math.abs(candidate.routeId() == null ? 0 : candidate.routeId().hashCode() % 17) * 0.001;
        return -evaluation.distanceKm()
                - evaluation.lateCount() * 1000.0
                - evaluation.totalLatenessMinutes() * 100.0
                - evaluation.capacityViolations() * 10000.0
                - evaluation.pickupDropoffViolations() * 10000.0
                + routeBias;
    }
}
