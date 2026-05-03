package com.routechain.v2.objective;

public record ObjectiveConfig(
        double scoreEpsilonPct,
        double minP95ImprovementSeconds,
        double maxMeanOtdRegressionSeconds,
        double maxDriverDetourRegressionSeconds,
        int maxRouteChurnStops) {

    public static ObjectiveConfig defaults() {
        return new ObjectiveConfig(1.0, 30.0, 10.0, 60.0, 2);
    }
}
