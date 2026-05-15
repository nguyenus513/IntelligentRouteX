package com.routechain.v2.hybrid;

import java.util.List;

public record SolutionSeedRoute(
        String routeId,
        String driverId,
        List<String> orderIds,
        List<String> stopSequence,
        double distanceKm,
        double durationMinutes,
        long lateOrderCount) {

    public SolutionSeedRoute {
        orderIds = orderIds == null ? List.of() : List.copyOf(orderIds);
        stopSequence = stopSequence == null ? List.of() : List.copyOf(stopSequence);
    }
}
