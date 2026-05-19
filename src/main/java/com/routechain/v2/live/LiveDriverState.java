package com.routechain.v2.live;

import java.time.Instant;

public record LiveDriverState(
        String driverId,
        double lat,
        double lng,
        String status,
        String currentStopId,
        Instant updatedAt) {
}
