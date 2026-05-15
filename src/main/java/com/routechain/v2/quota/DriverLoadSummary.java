package com.routechain.v2.quota;

public record DriverLoadSummary(
        String driverId,
        int assignedOrderCount,
        int minRequired,
        int targetOrderCount,
        int maxOrderCount,
        String status) {
}
