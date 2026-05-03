package com.routechain.v2.active;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.executor.DispatchAssignment;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public final class ActiveFleetStateStore {
    private static final Duration ACTIVE_ROUTE_TTL = Duration.ofMinutes(45);

    private final Map<String, ActiveRouteRecord> activeRouteByDriverId = new LinkedHashMap<>();
    private final Map<String, Order> orderSnapshotsById = new LinkedHashMap<>();

    public synchronized void recordAssignments(DispatchV2Request request, List<DispatchAssignment> assignments) {
        if (request == null || assignments == null || assignments.isEmpty()) {
            return;
        }
        Map<String, Order> requestOrderById = request.openOrders().stream()
                .collect(Collectors.toMap(Order::orderId, order -> order, (left, right) -> left, LinkedHashMap::new));
        Map<String, GeoPoint> driverLocationById = request.availableDrivers().stream()
                .collect(Collectors.toMap(Driver::driverId, Driver::currentLocation, (left, right) -> left, LinkedHashMap::new));
        for (DispatchAssignment assignment : assignments) {
            if (assignment == null || assignment.driverId() == null || assignment.orderIds().isEmpty()) {
                continue;
            }
            assignment.orderIds().stream()
                    .map(requestOrderById::get)
                    .forEach(order -> {
                        if (order != null) {
                            orderSnapshotsById.put(order.orderId(), order);
                        }
                    });
            GeoPoint currentLocation = driverLocationById.get(assignment.driverId());
            if (currentLocation == null) {
                continue;
            }
            activeRouteByDriverId.put(assignment.driverId(), new ActiveRouteRecord(
                    assignment.assignmentId(),
                    assignment.driverId(),
                    currentLocation,
                    assignment.orderIds(),
                    assignment.stopOrder(),
                    request.decisionTime(),
                    assignment.projectedCompletionEtaMinutes()));
        }
    }

    public synchronized List<ActiveRouteState> activeRoutes(DispatchV2Request request) {
        if (request == null || activeRouteByDriverId.isEmpty()) {
            return List.of();
        }
        pruneExpired(request.decisionTime());
        Map<String, GeoPoint> driverLocationById = request.availableDrivers().stream()
                .collect(Collectors.toMap(Driver::driverId, Driver::currentLocation, (left, right) -> left, LinkedHashMap::new));
        return activeRouteByDriverId.values().stream()
                .filter(record -> driverLocationById.containsKey(record.driverId()))
                .map(record -> record.toState(driverLocationById.get(record.driverId()), request.decisionTime()))
                .toList();
    }

    public synchronized List<Order> knownOrders(DispatchV2Request request) {
        LinkedHashMap<String, Order> known = new LinkedHashMap<>(orderSnapshotsById);
        if (request != null) {
            for (Order order : request.openOrders()) {
                known.put(order.orderId(), order);
            }
        }
        return List.copyOf(known.values());
    }

    public synchronized int size() {
        return activeRouteByDriverId.size();
    }

    public synchronized List<String> activeRouteIds() {
        return activeRouteByDriverId.values().stream()
                .map(ActiveRouteRecord::routeId)
                .sorted()
                .toList();
    }

    private void pruneExpired(Instant decisionTime) {
        if (decisionTime == null) {
            return;
        }
        Set<String> expiredDriverIds = activeRouteByDriverId.entrySet().stream()
                .filter(entry -> Duration.between(entry.getValue().updatedAt(), decisionTime).compareTo(ACTIVE_ROUTE_TTL) > 0)
                .map(Map.Entry::getKey)
                .collect(Collectors.toSet());
        expiredDriverIds.forEach(activeRouteByDriverId::remove);
        Set<String> activeOrderIds = activeRouteByDriverId.values().stream()
                .flatMap(record -> record.assignedOrderIds().stream())
                .collect(Collectors.toSet());
        new ArrayList<>(orderSnapshotsById.keySet()).stream()
                .filter(orderId -> !activeOrderIds.contains(orderId))
                .forEach(orderSnapshotsById::remove);
    }

    private record ActiveRouteRecord(
            String routeId,
            String driverId,
            GeoPoint currentLocation,
            List<String> assignedOrderIds,
            List<String> remainingStopOrder,
            Instant updatedAt,
            double projectedCompletionEtaMinutes) {

        private ActiveRouteRecord {
            assignedOrderIds = assignedOrderIds == null ? List.of() : List.copyOf(assignedOrderIds);
            remainingStopOrder = remainingStopOrder == null ? List.of() : List.copyOf(remainingStopOrder);
        }

        private ActiveRouteState toState(GeoPoint latestLocation, Instant decisionTime) {
            double ageMinutes = updatedAt == null || decisionTime == null
                    ? 0.0
                    : Math.max(0.0, Duration.between(updatedAt, decisionTime).toSeconds() / 60.0);
            double stabilityScore = Math.max(0.50, 1.0 - ageMinutes / 60.0);
            return new ActiveRouteState(
                    "active-route-state/v1",
                    routeId,
                    driverId,
                    latestLocation == null ? currentLocation : latestLocation,
                    assignedOrderIds,
                    remainingStopOrder,
                    updatedAt,
                    ageMinutes,
                    projectedCompletionEtaMinutes,
                    stabilityScore,
                    List.of("active-route-from-fleet-state-store"));
        }
    }
}
