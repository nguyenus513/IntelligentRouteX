package com.routechain.v2.rolling;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2Request;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RollingPendingOrderBufferTest {
    private final Instant now = Instant.parse("2026-04-29T00:00:00Z");

    @Test
    void heldOrderReturnsWhenReleaseTimeIsDue() {
        RollingPendingOrderBuffer buffer = new RollingPendingOrderBuffer();
        Order held = order("held");
        DispatchV2Request first = request(List.of(held), now);

        buffer.update(first, List.of(new RollingHoldDecision(
                "rolling-hold-decision/v1",
                held.orderId(),
                RollingDecisionMode.HOLD_SHORT,
                30,
                0.8,
                0.6,
                0.1,
                List.of("unit-hold"))));

        assertEquals(1, buffer.size());
        DispatchV2Request early = buffer.mergeDueOrders(request(List.of(), now.plusSeconds(20)));
        assertTrue(early.openOrders().isEmpty());

        DispatchV2Request due = buffer.mergeDueOrders(request(List.of(), now.plusSeconds(30)));
        assertEquals(List.of("held"), due.openOrders().stream().map(Order::orderId).toList());
    }

    @Test
    void dispatchDecisionRemovesBufferedOrder() {
        RollingPendingOrderBuffer buffer = new RollingPendingOrderBuffer();
        Order held = order("held");
        DispatchV2Request first = request(List.of(held), now);
        buffer.update(first, List.of(new RollingHoldDecision("rolling-hold-decision/v1", "held", RollingDecisionMode.HOLD_SHORT, 60, 0.8, 0.6, 0.1, List.of())));

        buffer.update(first, List.of(new RollingHoldDecision("rolling-hold-decision/v1", "held", RollingDecisionMode.DISPATCH_NOW, 0, 0.9, 0.3, 0.2, List.of())));

        assertEquals(0, buffer.size());
    }

    private DispatchV2Request request(List<Order> orders, Instant decisionTime) {
        return new DispatchV2Request(
                "dispatch-v2-request/v1",
                "trace-buffer",
                orders,
                List.of(new Driver("driver-1", new GeoPoint(0.0, 0.0))),
                List.of(),
                WeatherProfile.CLEAR,
                decisionTime);
    }

    private Order order(String orderId) {
        return new Order(
                orderId,
                new GeoPoint(0.0, 0.0),
                new GeoPoint(0.01, 0.0),
                now.minusSeconds(30),
                now.plusSeconds(60),
                45,
                false);
    }
}
