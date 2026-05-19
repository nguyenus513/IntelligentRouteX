package com.routechain.v2.live;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class FrozenStopPolicy {
    public List<String> frozenStops(List<LiveRouteSnapshot> routes, List<LiveDriverState> drivers) {
        List<String> frozen = new ArrayList<>();
        for (LiveRouteSnapshot route : routes == null ? List.<LiveRouteSnapshot>of() : routes) {
            if (route.stopIds() == null || route.stopIds().isEmpty()) {
                continue;
            }
            drivers.stream()
                    .filter(driver -> route.driverId().equals(driver.driverId()))
                    .findFirst()
                    .ifPresent(driver -> {
                        if (driver.currentStopId() != null && !driver.currentStopId().isBlank()) {
                            frozen.add(driver.currentStopId());
                        } else if (driver.status() != null && driver.status().toUpperCase(Locale.ROOT).contains("EN_ROUTE")) {
                            frozen.add(route.stopIds().getFirst());
                        }
                    });
            for (String stopId : route.stopIds()) {
                if (stopId != null && stopId.toUpperCase(Locale.ROOT).startsWith("PICKUP_DONE:")) {
                    frozen.add(stopId);
                }
            }
        }
        return frozen.stream().distinct().toList();
    }

    public int violations(List<String> previousFrozenStops, List<LiveRouteSnapshot> routes) {
        List<String> currentStops = (routes == null ? List.<LiveRouteSnapshot>of() : routes).stream()
                .flatMap(route -> route.stopIds().stream())
                .toList();
        int violations = 0;
        for (String stopId : previousFrozenStops == null ? List.<String>of() : previousFrozenStops) {
            if (!currentStops.contains(stopId)) {
                violations++;
            }
        }
        return violations;
    }
}
