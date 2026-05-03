package com.routechain.v2.selector;

public record HoldOrderDecision(
        String orderId,
        long holdSeconds,
        String reason,
        double penalty) {
}
