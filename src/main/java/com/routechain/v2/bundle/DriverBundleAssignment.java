package com.routechain.v2.bundle;

import java.util.List;

public record DriverBundleAssignment(
        String schemaVersion,
        String driverId,
        String routeId,
        String bundleId,
        List<String> orderIds,
        double cost,
        double insertCost,
        double latePenalty,
        double detourPenalty,
        double churnPenalty,
        double driverFit,
        double bundleScore,
        List<String> reasons) {

    public DriverBundleAssignment {
        orderIds = orderIds == null ? List.of() : List.copyOf(orderIds);
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
    }
}
