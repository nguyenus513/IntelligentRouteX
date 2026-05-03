package com.routechain.v2.repair;

import java.util.HashSet;

public final class SuffixStateScorer {
    public double score(MutableSuffixState state) {
        if (!state.feasible() || state.mutableStops().isEmpty() || !state.mutableStops().contains(state.insertedOrderId())) {
            return 0.0;
        }
        int uniqueCount = new HashSet<>(state.mutableStops()).size();
        double duplicatePenalty = Math.max(0, state.mutableStops().size() - uniqueCount) * 0.08;
        double insertedPositionPenalty = state.mutableStops().indexOf(state.insertedOrderId()) * 0.015;
        double removedPenalty = state.removedStops().size() * 0.02;
        double compactnessReward = Math.min(0.08, uniqueCount * 0.01);
        return Math.max(0.0, Math.min(1.0, state.score() + compactnessReward - duplicatePenalty - insertedPositionPenalty - removedPenalty));
    }
}
