package com.routechain.v2.routing;

import java.util.List;

public record RoutingSnapResult(
        String schemaVersion,
        String provider,
        String status,
        double rawLatitude,
        double rawLongitude,
        double snappedLatitude,
        double snappedLongitude,
        double snapDistanceMeters,
        double snapConfidence,
        String roadNodeId,
        String roadEdgeId,
        List<String> degradeReasons) {

    public RoutingSnapResult {
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }
}
