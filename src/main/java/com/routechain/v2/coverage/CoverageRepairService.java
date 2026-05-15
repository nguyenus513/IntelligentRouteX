package com.routechain.v2.coverage;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.v2.executor.DispatchAssignment;
import com.routechain.v2.executor.ExecutionActionType;
import com.routechain.v2.route.RouteProposalSource;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

public final class CoverageRepairService {
    public List<DispatchAssignment> repair(List<DispatchAssignment> existingAssignments, List<Order> allOrders, List<Driver> allDrivers, Map<String, Integer> driverLoads, int maxOrdersPerDriver) {
        List<DispatchAssignment> repaired = new ArrayList<>(existingAssignments == null ? List.of() : existingAssignments);
        Map<String, Order> orderById = new LinkedHashMap<>();
        allOrders.forEach(order -> orderById.put(order.orderId(), order));
        Set<String> assigned = new LinkedHashSet<>();
        repaired.forEach(assignment -> assigned.addAll(assignment.orderIds()));
        Map<String, List<String>> additionsByDriver = new LinkedHashMap<>();
        allDrivers.forEach(driver -> additionsByDriver.put(driver.driverId(), new ArrayList<>()));
        for (Order order : allOrders) {
            if (assigned.contains(order.orderId())) {
                continue;
            }
            Optional<Driver> selected = allDrivers.stream()
                    .filter(driver -> driverLoads.getOrDefault(driver.driverId(), 0) < maxOrdersPerDriver)
                    .min(Comparator.comparingDouble(driver -> insertionCost(order, driver, repaired, additionsByDriver, orderById, driverLoads)));
            if (selected.isEmpty()) {
                selected = allDrivers.stream().min(Comparator.comparingDouble(driver -> insertionCost(order, driver, repaired, additionsByDriver, orderById, driverLoads)));
            }
            selected.ifPresent(driver -> {
                additionsByDriver.get(driver.driverId()).add(order.orderId());
                driverLoads.put(driver.driverId(), driverLoads.getOrDefault(driver.driverId(), 0) + 1);
            });
        }
        int rank = repaired.size();
        for (Driver driver : allDrivers) {
            List<String> orderIds = additionsByDriver.getOrDefault(driver.driverId(), List.of());
            if (orderIds.isEmpty()) {
                continue;
            }
            repaired.add(newAssignment("repair-" + driver.driverId(), driver.driverId(), orderIds, rank++, AssignmentSource.BALANCED_COVERAGE_REPAIR));
        }
        return repaired;
    }

    private static double insertionCost(Order order,
                                        Driver driver,
                                        List<DispatchAssignment> existingAssignments,
                                        Map<String, List<String>> additionsByDriver,
                                        Map<String, Order> orderById,
                                        Map<String, Integer> driverLoads) {
        GeoPoint start = routeTail(driver, existingAssignments, additionsByDriver.getOrDefault(driver.driverId(), List.of()), orderById);
        double appendCost = distanceKm(start, order.pickupPoint()) + distanceKm(order.pickupPoint(), order.dropoffPoint());
        double loadPenalty = driverLoads.getOrDefault(driver.driverId(), 0) * 0.35;
        return appendCost + loadPenalty;
    }

    private static GeoPoint routeTail(Driver driver, List<DispatchAssignment> assignments, List<String> pendingOrderIds, Map<String, Order> orderById) {
        GeoPoint tail = driver.currentLocation();
        for (DispatchAssignment assignment : assignments) {
            if (!assignment.driverId().equals(driver.driverId())) {
                continue;
            }
            for (String orderId : assignment.orderIds()) {
                Order order = orderById.get(orderId);
                if (order != null) {
                    tail = order.dropoffPoint();
                }
            }
        }
        for (String orderId : pendingOrderIds) {
            Order order = orderById.get(orderId);
            if (order != null) {
                tail = order.dropoffPoint();
            }
        }
        return tail;
    }

    public DispatchAssignment singletonFallback(Order order, Driver driver, int rank) {
        return newAssignment("singleton-" + order.orderId(), driver.driverId(), List.of(order.orderId()), rank, AssignmentSource.SINGLETON_FALLBACK);
    }

    private static DispatchAssignment newAssignment(String prefix, String driverId, List<String> orderIds, int rank, AssignmentSource source) {
        List<String> stopOrder = new ArrayList<>();
        orderIds.forEach(orderId -> stopOrder.add("PICKUP:" + orderId));
        orderIds.forEach(orderId -> stopOrder.add("DROPOFF:" + orderId));
        double eta = Math.max(8.0, orderIds.size() * 12.0);
        return new DispatchAssignment(
                "dispatch-assignment/v1",
                prefix + "-" + driverId,
                prefix + "-proposal-" + driverId,
                prefix + "-batch-" + driverId,
                orderIds.getFirst(),
                driverId,
                List.copyOf(orderIds),
                stopOrder,
                ExecutionActionType.ASSIGN_DRIVER,
                RouteProposalSource.FALLBACK_SIMPLE,
                rank,
                Math.max(1.0, 100.0 - rank),
                Math.max(1.0, 100.0 - orderIds.size()),
                eta / 2.0,
                eta,
                Math.max(1.0, 100.0 - orderIds.size()),
                source.name(),
                false,
                Instant.now(),
                Instant.now().plusSeconds((long) eta * 60L),
                List.of(source.name().toLowerCase().replace('_', '-'), "core-owned-coverage"),
                List.of());
    }

    private static double distanceKm(GeoPoint a, GeoPoint b) {
        double earthRadiusKm = 6371.0;
        double dLat = Math.toRadians(b.latitude() - a.latitude());
        double dLng = Math.toRadians(b.longitude() - a.longitude());
        double lat1 = Math.toRadians(a.latitude());
        double lat2 = Math.toRadians(b.latitude());
        double sinLat = Math.sin(dLat / 2.0);
        double sinLng = Math.sin(dLng / 2.0);
        double h = sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLng * sinLng;
        return earthRadiusKm * 2.0 * Math.atan2(Math.sqrt(h), Math.sqrt(1.0 - h));
    }
}

