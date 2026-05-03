package com.routechain.v2.rolling;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record RollingOrderState(
        String schemaVersion,
        String orderId,
        long orderAgeSeconds,
        long readySlackSeconds,
        long promiseSlackSeconds,
        double nearbyOrderDensity,
        double bundleOpportunityScore,
        double nearestDriverScore,
        boolean urgent,
        boolean ready,
        List<String> reasonCodes) implements SchemaVersioned {

    public RollingOrderState {
        reasonCodes = reasonCodes == null ? List.of() : List.copyOf(reasonCodes);
    }
}
