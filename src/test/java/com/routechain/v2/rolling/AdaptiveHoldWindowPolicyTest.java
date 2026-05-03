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

class AdaptiveHoldWindowPolicyTest {
    private final AdaptiveHoldWindowPolicy policy = new AdaptiveHoldWindowPolicy();
    private final Instant now = Instant.parse("2026-04-29T00:00:00Z");

    @Test
    void urgentOrderDispatchesNow() {
        Order urgent = order("urgent", 0.0, 0.0, 0.01, 0.0, now.minusSeconds(60), now.plusSeconds(120), 25, true);

        RollingHoldDecision decision = decide(List.of(urgent), driversNear(), WeatherProfile.CLEAR).getFirst();

        assertEquals(RollingDecisionMode.DISPATCH_NOW, decision.decisionMode());
        assertEquals(0L, decision.holdSeconds());
        assertTrue(decision.reasonCodes().contains("dispatch-now-urgent-or-low-promise-slack"));
    }

    @Test
    void sparseOrderDoesNotWaitForLargeBatch() {
        Order sparse = order("sparse", 0.0, 0.0, 0.02, 0.0, now.minusSeconds(30), now.minusSeconds(10), 45, false);

        RollingHoldDecision decision = decide(List.of(sparse), driversNear(), WeatherProfile.CLEAR).getFirst();

        assertEquals(RollingDecisionMode.DISPATCH_NOW, decision.decisionMode());
        assertEquals(0L, decision.holdSeconds());
        assertTrue(decision.reasonCodes().contains("dispatch-now-sparse-or-low-opportunity"));
    }

    @Test
    void denseCompatibleOrdersEnterMicroBatch() {
        List<Order> orders = List.of(
                order("a", 0.0, 0.0, 0.03, 0.0, now.minusSeconds(30), now.plusSeconds(180), 60, false),
                order("b", 0.005, 0.002, 0.035, 0.002, now.minusSeconds(20), now.plusSeconds(210), 60, false),
                order("c", 0.006, 0.001, 0.034, 0.001, now.minusSeconds(10), now.plusSeconds(240), 60, false));

        List<RollingHoldDecision> decisions = decide(orders, driversNear(), WeatherProfile.CLEAR);

        assertTrue(decisions.stream().anyMatch(decision -> decision.decisionMode() == RollingDecisionMode.MICRO_BATCH));
        assertTrue(decisions.stream().filter(decision -> decision.decisionMode() == RollingDecisionMode.MICRO_BATCH).allMatch(decision -> decision.holdSeconds() > 0L));
    }

    @Test
    void heavyRainReducesHoldWhenOpportunityIsNotStrong() {
        List<Order> orders = List.of(
                order("a", 0.0, 0.0, 0.02, 0.0, now.minusSeconds(30), now.plusSeconds(180), 55, false),
                order("b", 0.018, 0.001, -0.02, 0.0, now.minusSeconds(20), now.plusSeconds(210), 55, false));

        RollingHoldDecision decision = decide(orders, driversNear(), WeatherProfile.HEAVY_RAIN).stream()
                .filter(row -> row.orderId().equals("a"))
                .findFirst()
                .orElseThrow();

        assertEquals(RollingDecisionMode.DISPATCH_NOW, decision.decisionMode());
        assertTrue(decision.reasonCodes().contains("dispatch-now-weather-risk"));
    }

    private List<RollingHoldDecision> decide(List<Order> orders, List<Driver> drivers, WeatherProfile weatherProfile) {
        DispatchV2Request request = new DispatchV2Request(
                "dispatch-v2-request/v1",
                "trace-1",
                orders,
                drivers,
                List.of(),
                weatherProfile,
                now);
        return policy.decide(RollingDispatchState.fromRequest(request));
    }

    private List<Driver> driversNear() {
        return List.of(new Driver("driver-1", new GeoPoint(0.001, 0.001)));
    }

    private Order order(String orderId,
                        double pickupLat,
                        double pickupLon,
                        double dropoffLat,
                        double dropoffLon,
                        Instant createdAt,
                        Instant readyAt,
                        int promisedEtaMinutes,
                        boolean urgent) {
        return new Order(
                orderId,
                new GeoPoint(pickupLat, pickupLon),
                new GeoPoint(dropoffLat, dropoffLon),
                createdAt,
                readyAt,
                promisedEtaMinutes,
                urgent);
    }
}
