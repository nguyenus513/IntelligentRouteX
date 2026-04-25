package com.routechain.v2.routing;

import java.util.List;

public record MatrixPoint(
        String pointId,
        double rawLatitude,
        double rawLongitude,
        double snappedLatitude,
        double snappedLongitude,
        double snapDistanceMeters,
        String osrmName,
        List<String> degradeReasons) {

    public MatrixPoint {
        pointId = pointId == null || pointId.isBlank() ? "point" : pointId;
        osrmName = osrmName == null ? "" : osrmName;
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }

    static MatrixPoint unsnapped(RouteStop stop, String reason) {
        return new MatrixPoint(
                stop.stopId(),
                stop.latitude(),
                stop.longitude(),
                stop.latitude(),
                stop.longitude(),
                0.0,
                "",
                List.of(reason));
    }
}
