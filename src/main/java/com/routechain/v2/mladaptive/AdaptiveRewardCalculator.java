package com.routechain.v2.mladaptive;

public final class AdaptiveRewardCalculator {
    public double reward(double coverageDelta,
                         int hardViolationDelta,
                         long lateDelta,
                         double totalLatenessDelta,
                         double distanceImprovementKm,
                         long runtimeMs) {
        double value = coverageDelta * 1000.0
                - hardViolationDelta * 1000.0
                - lateDelta * 200.0
                - totalLatenessDelta * 20.0
                + distanceImprovementKm * 10.0
                - runtimeMs * 0.001;
        if (hardViolationDelta > 0 || lateDelta > 0) {
            value -= 500.0;
        }
        return Math.round(value * 1000.0) / 1000.0;
    }
}
