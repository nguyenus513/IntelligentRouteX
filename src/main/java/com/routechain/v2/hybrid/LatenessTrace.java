package com.routechain.v2.hybrid;

public record LatenessTrace(
        String routeId,
        String orderId,
        String moveId,
        String moveType,
        double oldEtaMinutes,
        double newEtaMinutes,
        double dueTimeMinutes,
        double oldSlackMinutes,
        double newSlackMinutes,
        double latenessMinutes,
        String reason) {
}
