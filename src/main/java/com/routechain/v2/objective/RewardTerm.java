package com.routechain.v2.objective;

public record RewardTerm(
        double batchingReward,
        double diversityReward,
        double coverageReward) {

    public double total() {
        return batchingReward + diversityReward + coverageReward;
    }
}
