package com.routechain.v2.selector;

public record RejectedOrderDecision(
        String orderId,
        String reason,
        double penalty) {
}
