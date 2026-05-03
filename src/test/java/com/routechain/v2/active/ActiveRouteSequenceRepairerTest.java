package com.routechain.v2.active;

import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ActiveRouteSequenceRepairerTest {

    private final ActiveRouteSequenceRepairer repairer = new ActiveRouteSequenceRepairer();

    @Test
    void improvesGeometryWithoutBreakingPickupDropoffPrecedence() {
        Order near = order("near", 0.1, 0.0, 0.2, 0.0);
        Order far = order("far", 10.0, 0.0, 10.2, 0.0);
        List<ActiveRouteStop> badSequence = List.of(
                ActiveRouteStop.pickup(far),
                ActiveRouteStop.pickup(near),
                ActiveRouteStop.dropoff(far),
                ActiveRouteStop.dropoff(near));

        ActiveRouteSequenceRepairResult result = repairer.repair(new GeoPoint(0.0, 0.0), badSequence);

        assertTrue(result.movesTried() > 0);
        assertTrue(result.distanceDelta() >= 0.0);
        assertPrecedence(result.stopSequence());
        assertTrue(result.reasons().stream().anyMatch(reason -> reason.startsWith("active-sequence-")));
    }

    @Test
    void skipsSmallRoutes() {
        Order order = order("order-1", 0.1, 0.0, 0.2, 0.0);

        ActiveRouteSequenceRepairResult result = repairer.repair(new GeoPoint(0.0, 0.0), List.of(
                ActiveRouteStop.pickup(order),
                ActiveRouteStop.dropoff(order)));

        assertEquals(0, result.movesTried());
        assertTrue(result.reasons().contains("active-sequence-repair-skipped-small-route"));
    }

    private void assertPrecedence(List<ActiveRouteStop> sequence) {
        java.util.HashSet<String> pickedUp = new java.util.HashSet<>();
        for (ActiveRouteStop stop : sequence) {
            if (stop.stopType() == ActiveRouteStopType.PICKUP) {
                pickedUp.add(stop.orderId());
            } else {
                assertTrue(pickedUp.contains(stop.orderId()));
            }
        }
    }

    private Order order(String orderId, double pickupLat, double pickupLon, double dropoffLat, double dropoffLon) {
        Instant readyAt = Instant.parse("2026-04-16T12:00:00Z");
        return new Order(
                orderId,
                new GeoPoint(pickupLat, pickupLon),
                new GeoPoint(dropoffLat, dropoffLon),
                readyAt.minusSeconds(300),
                readyAt,
                30,
                false);
    }
}
