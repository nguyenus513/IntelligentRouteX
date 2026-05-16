package com.routechain.v2.live;

import java.time.Instant;

public record LiveOrderState(
        LiveOrderSnapshot order,
        LiveOrderStatus status,
        Instant createdAt,
        Instant updatedAt,
        int deferCount,
        String reason) {
}
