package com.routechain.v2.hybrid;

import java.util.Comparator;

public final class LexicographicSolutionComparator implements Comparator<SolutionSeedCandidate> {
    public static final LexicographicSolutionComparator SLA_STRICT = new LexicographicSolutionComparator();

    @Override
    public int compare(SolutionSeedCandidate left, SolutionSeedCandidate right) {
        if (left == right) {
            return 0;
        }
        if (left == null) {
            return -1;
        }
        if (right == null) {
            return 1;
        }
        int coverage = Double.compare(left.coverageRate(), right.coverageRate());
        if (coverage != 0) {
            return coverage;
        }
        int hardFeasible = Boolean.compare(left.hardFeasible(), right.hardFeasible());
        if (hardFeasible != 0) {
            return hardFeasible;
        }
        int late = Long.compare(right.lateOrderCount(), left.lateOrderCount());
        if (late != 0) {
            return late;
        }
        int latenessCost = Double.compare(right.costBreakdown().latenessCost(), left.costBreakdown().latenessCost());
        if (latenessCost != 0) {
            return latenessCost;
        }
        int distance = Double.compare(right.totalDistanceKm(), left.totalDistanceKm());
        if (distance != 0) {
            return distance;
        }
        int loadPenalty = Double.compare(right.costBreakdown().loadPenalty(), left.costBreakdown().loadPenalty());
        if (loadPenalty != 0) {
            return loadPenalty;
        }
        return Double.compare(left.costBreakdown().finalScore(), right.costBreakdown().finalScore());
    }

    public SolutionSeedCandidate better(SolutionSeedCandidate left, SolutionSeedCandidate right) {
        return compare(left, right) >= 0 ? left : right;
    }

    public String reason(SolutionSeedCandidate selected, SolutionSeedCandidate rejected) {
        if (selected == null || rejected == null) {
            return "missing-seed";
        }
        if (selected.coverageRate() != rejected.coverageRate()) {
            return "higher-coverage-rate";
        }
        if (selected.hardFeasible() != rejected.hardFeasible()) {
            return "hard-feasible-seed";
        }
        if (selected.lateOrderCount() != rejected.lateOrderCount()) {
            return "lower-late-order-count";
        }
        if (selected.costBreakdown().latenessCost() != rejected.costBreakdown().latenessCost()) {
            return "lower-total-lateness-cost";
        }
        if (selected.totalDistanceKm() != rejected.totalDistanceKm()) {
            return "lower-distance-with-same-sla";
        }
        return "higher-final-score-tiebreak";
    }
}
