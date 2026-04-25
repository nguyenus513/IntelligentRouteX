package com.routechain.v2.routing;

import java.util.List;

public record RoutingRouteResult(
        String schemaVersion,
        String provider,
        String geometryKind,
        LegRouteVector legVector,
        double corridorPreferenceScore,
        List<RoutePolylinePoint> polyline,
        List<String> degradeReasons) {

    public RoutingRouteResult {
        polyline = polyline == null ? List.of() : List.copyOf(polyline);
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }
}
