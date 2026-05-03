package com.routechain.v2.active;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.executor.DispatchAssignment;
import com.routechain.v2.executor.ExecutionActionType;
import com.routechain.v2.route.RouteProposalSource;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ActiveFleetStateStoreTest {

    @Test
    void recordsAssignmentsAndBuildsActiveRouteStateFromLatestDriverLocation() {
        ActiveFleetStateStore store = new ActiveFleetStateStore();
        Instant decisionTime = Instant.parse("2026-04-16T12:00:00Z");
        DispatchV2Request firstRequest = request(
                decisionTime,
                new Driver("driver-1", new GeoPoint(10.7700, 106.7000)),
                List.of(order("order-1", decisionTime)));
        store.recordAssignments(firstRequest, List.of(assignment("assignment-1", "driver-1", List.of("order-1"))));

        DispatchV2Request nextRequest = request(
                decisionTime.plusSeconds(120),
                new Driver("driver-1", new GeoPoint(10.7710, 106.7010)),
                List.of(order("order-2", decisionTime.plusSeconds(120))));

        List<ActiveRouteState> activeRoutes = store.activeRoutes(nextRequest);

        assertEquals(1, activeRoutes.size());
        assertEquals("assignment-1", activeRoutes.getFirst().routeId());
        assertEquals(new GeoPoint(10.7710, 106.7010), activeRoutes.getFirst().currentLocation());
        assertEquals(List.of("order-1"), activeRoutes.getFirst().remainingStopOrder());
        assertTrue(store.knownOrders(nextRequest).stream().map(Order::orderId).toList().containsAll(List.of("order-1", "order-2")));
    }

    private DispatchV2Request request(Instant decisionTime, Driver driver, List<Order> orders) {
        return new DispatchV2Request(
                "dispatch-v2-request/v1",
                "trace-active-store",
                orders,
                List.of(driver),
                List.of(),
                WeatherProfile.CLEAR,
                decisionTime);
    }

    private Order order(String orderId, Instant readyAt) {
        return new Order(
                orderId,
                new GeoPoint(10.7750, 106.7000),
                new GeoPoint(10.7800, 106.7100),
                readyAt.minusSeconds(300),
                readyAt,
                30,
                false);
    }

    private DispatchAssignment assignment(String assignmentId, String driverId, List<String> orderIds) {
        return new DispatchAssignment(
                "dispatch-assignment/v1",
                assignmentId,
                "proposal-1",
                "bundle-1",
                orderIds.getFirst(),
                driverId,
                orderIds,
                orderIds,
                ExecutionActionType.ASSIGN_DRIVER,
                RouteProposalSource.HEURISTIC_FAST,
                1,
                0.90,
                0.90,
                4.0,
                18.0,
                0.80,
                "cluster-1",
                false,
                Instant.parse("2026-04-16T12:00:00Z"),
                Instant.parse("2026-04-16T12:05:00Z"),
                List.of(),
                List.of());
    }
}
