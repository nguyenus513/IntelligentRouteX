package com.routechain.v2.live;

public record LiveOrderSnapshot(
        String orderId,
        double pickupLat,
        double pickupLng,
        double dropoffLat,
        double dropoffLng,
        int deadlineMinutes,
        int priority) {
}
