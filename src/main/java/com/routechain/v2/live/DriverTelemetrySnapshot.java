package com.routechain.v2.live;

import java.time.Instant;

public record DriverTelemetrySnapshot(
        String driverId,
        double lat,
        double lng,
        Instant timestamp,
        double heading,
        double speed,
        String activeRouteId,
        String status) {
}
