package com.routechain.v2.seedimprovement;

import java.util.List;

public record PdValidationResult(
        boolean valid,
        int pickupDropoffViolations,
        int capacityViolations,
        int missingPickup,
        int missingDropoff,
        int duplicateStop,
        int assignedOrderCount,
        long lateCount,
        double distanceKm,
        List<String> reasons) {

    public PdValidationResult {
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
    }
}
