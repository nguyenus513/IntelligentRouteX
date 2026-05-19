package com.routechain.v2.live;

import java.util.List;

public record LiveRouteSnapshot(
        String routeId,
        String driverId,
        List<String> stopIds,
        List<String> frozenStopIds,
        double distanceKm,
        int lateCount) {
}
