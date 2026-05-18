package com.routechain.v2.seedimprovement;

public record PdLnsTrace(
        int round,
        String orderId,
        String operator,
        boolean accepted,
        double oldKm,
        double newKm,
        double gainKm,
        int evaluatedInsertions,
        int feasibleInsertions,
        String rejectReason) {
}
