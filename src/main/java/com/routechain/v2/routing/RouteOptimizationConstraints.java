package com.routechain.v2.routing;

public record RouteOptimizationConstraints(
        double maxRouteDurationSeconds,
        double maxDetourRatioPerOrder,
        int topK) {

    public RouteOptimizationConstraints {
        maxRouteDurationSeconds = maxRouteDurationSeconds <= 0.0 ? 2700.0 : maxRouteDurationSeconds;
        maxDetourRatioPerOrder = maxDetourRatioPerOrder <= 0.0 ? 0.60 : maxDetourRatioPerOrder;
        topK = topK <= 0 ? 3 : topK;
    }

    public static RouteOptimizationConstraints defaults() {
        return new RouteOptimizationConstraints(2700.0, 0.60, 3);
    }
}
