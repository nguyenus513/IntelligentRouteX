package com.routechain.v2.benchmark;

import com.routechain.v2.SchemaVersioned;

public record DispatchRouteVectorMetrics(
        String schemaVersion,
        int proposalCount,
        double geometryCoverage,
        double averageTotalDistanceMeters,
        double averageTotalTravelTimeSeconds,
        double averageRouteCost,
        double averageCongestionScore,
        double averageMajorRoadRatio,
        double averageStraightnessScore,
        double averageTurnCount,
        double routeDominanceRate,
        double averageRouteRegret,
        double averagePathEfficiency,
        double averageEtaDominanceScore) implements SchemaVersioned {

    public static DispatchRouteVectorMetrics empty() {
        return new DispatchRouteVectorMetrics(
                "dispatch-route-vector-metrics/v1",
                0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0);
    }
}
