package com.routechain.v2.coverage;

public record PassSummary(
        int passIndex,
        String strategy,
        int inputOrders,
        int eligibleDrivers,
        int assignedOrders,
        int remainingOrders,
        long runtimeMs) {
}
