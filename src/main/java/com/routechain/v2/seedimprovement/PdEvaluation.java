package com.routechain.v2.seedimprovement;

public record PdEvaluation(
        boolean valid,
        int assignedCount,
        int lateCount,
        double totalLatenessMinutes,
        double distanceKm,
        double durationMinutes,
        int pickupDropoffViolations,
        int capacityViolations,
        int duplicateStopViolations,
        int missingStopViolations,
        String rejectReason) {

    public boolean hasHardViolation() {
        return pickupDropoffViolations > 0
                || capacityViolations > 0
                || duplicateStopViolations > 0
                || missingStopViolations > 0;
    }
}
