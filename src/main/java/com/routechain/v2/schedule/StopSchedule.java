package com.routechain.v2.schedule;

import com.routechain.v2.hybrid.StopType;

public record StopSchedule(
        String stopId,
        String orderId,
        StopType stopType,
        double etaMinutes,
        double serviceCompleteMinutes,
        double distanceFromPreviousKm) {
}
