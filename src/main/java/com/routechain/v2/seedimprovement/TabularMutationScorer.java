package com.routechain.v2.seedimprovement;

import java.util.List;

public final class TabularMutationScorer {
    public double score(PdEvaluation current, PdEvaluation candidate, List<String> orderIds, int destroySize, String operator) {
        if (current == null || candidate == null || !candidate.valid()) {
            return Double.NEGATIVE_INFINITY;
        }
        double estimatedDeltaKm = current.distanceKm() - candidate.distanceKm();
        double latePenalty = Math.max(0, candidate.lateCount() - current.lateCount()) * 1000.0;
        double latenessPenalty = Math.max(0.0, candidate.totalLatenessMinutes() - current.totalLatenessMinutes()) * 100.0;
        double coveragePenalty = Math.max(0, current.assignedCount() - candidate.assignedCount()) * 10000.0;
        double capacityPenalty = candidate.capacityViolations() * 10000.0;
        double pdPenalty = candidate.pickupDropoffViolations() * 10000.0;
        double clusterBonus = Math.min(2.0, Math.max(0, orderIds == null ? 0 : orderIds.size()) * 0.20);
        double operatorBonus = operator != null && operator.contains("SWAP") ? 0.30 : operator != null && operator.contains("CROSS") ? 0.20 : 0.10;
        return round(estimatedDeltaKm * 10.0 + clusterBonus + operatorBonus + destroySize * 0.05 - latePenalty - latenessPenalty - coveragePenalty - capacityPenalty - pdPenalty);
    }

    private double round(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }
}
