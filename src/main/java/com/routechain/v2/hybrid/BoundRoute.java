package com.routechain.v2.hybrid;

import java.util.List;

public record BoundRoute(
        String routeId,
        String driverId,
        List<String> orderIds,
        List<BoundStop> stops,
        double distanceKm,
        double durationMinutes,
        int lateOrderCount) {

    public BoundRoute {
        orderIds = orderIds == null ? List.of() : List.copyOf(orderIds);
        stops = stops == null ? List.of() : List.copyOf(stops);
    }
}
