package com.routechain.v2.routing;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class PickupDeliveryPermutationOptimizer {

    public List<RouteSequence> optimize(RouteStop driverStop,
                                        List<PickupDeliveryStop> pickupStops,
                                        List<PickupDeliveryStop> dropoffStops,
                                        DurationMatrix matrix,
                                        RouteOptimizationConstraints constraints) {
        RouteOptimizationConstraints safeConstraints = constraints == null ? RouteOptimizationConstraints.defaults() : constraints;
        if (driverStop == null || pickupStops == null || dropoffStops == null || matrix == null) {
            return List.of();
        }
        List<PickupDeliveryStop> pickups = pickupStops.stream()
                .filter(stop -> stop.kind() == PickupDeliveryStop.StopKind.PICKUP)
                .sorted(Comparator.comparing(PickupDeliveryStop::stopId))
                .toList();
        List<PickupDeliveryStop> dropoffs = dropoffStops.stream()
                .filter(stop -> stop.kind() == PickupDeliveryStop.StopKind.DROPOFF)
                .sorted(Comparator.comparing(PickupDeliveryStop::stopId))
                .toList();
        if (pickups.isEmpty() || pickups.size() != dropoffs.size() || pickups.size() > 5) {
            return List.of();
        }
        Map<String, PickupDeliveryStop> dropoffByOrder = dropoffs.stream()
                .collect(java.util.stream.Collectors.toMap(PickupDeliveryStop::orderId, stop -> stop, (left, right) -> left));
        if (pickups.stream().anyMatch(pickup -> !dropoffByOrder.containsKey(pickup.orderId()))) {
            return List.of();
        }
        MatrixIndex index = MatrixIndex.from(matrix);
        List<PickupDeliveryStop> allStops = new ArrayList<>(pickups.size() + dropoffs.size());
        allStops.addAll(pickups);
        allStops.addAll(dropoffs);
        List<RouteSequence> results = new ArrayList<>();
        search(
                driverStop.stopId(),
                allStops,
                index,
                new ArrayList<>(),
                new HashSet<>(),
                new HashSet<>(),
                0.0,
                0.0,
                results,
                safeConstraints);
        return results.stream()
                .sorted(Comparator.comparing(RouteSequence::feasible).reversed()
                        .thenComparingDouble(RouteSequence::score))
                .limit(safeConstraints.topK())
                .toList();
    }

    private void search(String currentStopId,
                        List<PickupDeliveryStop> allStops,
                        MatrixIndex index,
                        List<PickupDeliveryStop> path,
                        Set<String> visitedStopIds,
                        Set<String> pickedOrderIds,
                        double durationSeconds,
                        double distanceMeters,
                        List<RouteSequence> results,
                        RouteOptimizationConstraints constraints) {
        if (durationSeconds > constraints.maxRouteDurationSeconds()) {
            return;
        }
        if (path.size() == allStops.size()) {
            results.add(evaluate(path, durationSeconds, distanceMeters, index, constraints));
            return;
        }
        for (PickupDeliveryStop next : allStops) {
            if (visitedStopIds.contains(next.stopId())) {
                continue;
            }
            if (next.kind() == PickupDeliveryStop.StopKind.DROPOFF && !pickedOrderIds.contains(next.orderId())) {
                continue;
            }
            Double legDuration = index.duration(currentStopId, next.stopId());
            if (legDuration == null) {
                continue;
            }
            Double legDistance = index.distance(currentStopId, next.stopId());
            path.add(next);
            visitedStopIds.add(next.stopId());
            boolean addedPickup = false;
            if (next.kind() == PickupDeliveryStop.StopKind.PICKUP) {
                addedPickup = pickedOrderIds.add(next.orderId());
            }
            search(
                    next.stopId(),
                    allStops,
                    index,
                    path,
                    visitedStopIds,
                    pickedOrderIds,
                    durationSeconds + legDuration,
                    distanceMeters + (legDistance == null ? 0.0 : legDistance),
                    results,
                    constraints);
            if (addedPickup) {
                pickedOrderIds.remove(next.orderId());
            }
            visitedStopIds.remove(next.stopId());
            path.removeLast();
        }
    }

    private RouteSequence evaluate(List<PickupDeliveryStop> path,
                                   double durationSeconds,
                                   double distanceMeters,
                                   MatrixIndex index,
                                   RouteOptimizationConstraints constraints) {
        Map<String, Double> actualByOrder = new HashMap<>();
        for (int left = 0; left < path.size(); left++) {
            PickupDeliveryStop leftStop = path.get(left);
            if (leftStop.kind() != PickupDeliveryStop.StopKind.PICKUP) {
                continue;
            }
            double elapsed = 0.0;
            String previousStopId = leftStop.stopId();
            for (int right = left + 1; right < path.size(); right++) {
                PickupDeliveryStop rightStop = path.get(right);
                Double leg = index.duration(previousStopId, rightStop.stopId());
                if (leg == null) {
                    elapsed = Double.POSITIVE_INFINITY;
                    break;
                }
                elapsed += leg;
                if (rightStop.kind() == PickupDeliveryStop.StopKind.DROPOFF && rightStop.orderId().equals(leftStop.orderId())) {
                    actualByOrder.put(leftStop.orderId(), elapsed);
                    break;
                }
                previousStopId = rightStop.stopId();
            }
        }
        Map<String, Double> detourByOrder = new HashMap<>();
        List<String> rejectReasons = new ArrayList<>();
        for (PickupDeliveryStop stop : path) {
            if (stop.kind() != PickupDeliveryStop.StopKind.PICKUP) {
                continue;
            }
            Double direct = index.duration(stop.stopId(), stop.orderId() + ":dropoff");
            Double actual = actualByOrder.get(stop.orderId());
            if (direct == null || direct <= 0.0 || actual == null || !Double.isFinite(actual)) {
                rejectReasons.add("MATRIX_UNREACHABLE");
                continue;
            }
            double detour = Math.max(0.0, (actual - direct) / direct);
            detourByOrder.put(stop.orderId(), detour);
            if (detour > constraints.maxDetourRatioPerOrder()) {
                rejectReasons.add("DETOUR_TOO_HIGH");
            }
        }
        if (durationSeconds > constraints.maxRouteDurationSeconds()) {
            rejectReasons.add("DURATION_EXCEEDED");
        }
        double averageDetour = detourByOrder.values().stream().mapToDouble(Double::doubleValue).average().orElse(0.0);
        double maxDetour = detourByOrder.values().stream().mapToDouble(Double::doubleValue).max().orElse(0.0);
        double score = durationSeconds + (averageDetour * 900.0) + (maxDetour * 600.0);
        boolean feasible = rejectReasons.isEmpty();
        return new RouteSequence(
                "route-sequence/v1",
                List.copyOf(path),
                durationSeconds,
                distanceMeters,
                averageDetour,
                maxDetour,
                score,
                feasible,
                rejectReasons.stream().distinct().toList(),
                detourByOrder);
    }

    private record MatrixIndex(Map<String, Integer> sourceIndex, Map<String, Integer> destinationIndex, DurationMatrix matrix) {
        static MatrixIndex from(DurationMatrix matrix) {
            Map<String, Integer> sources = new HashMap<>();
            for (int index = 0; index < matrix.sourceStops().size(); index++) {
                sources.put(matrix.sourceStops().get(index).stopId(), index);
            }
            Map<String, Integer> destinations = new HashMap<>();
            for (int index = 0; index < matrix.destinationStops().size(); index++) {
                destinations.put(matrix.destinationStops().get(index).stopId(), index);
            }
            return new MatrixIndex(sources, destinations, matrix);
        }

        Double duration(String fromStopId, String toStopId) {
            Integer source = sourceIndex.get(fromStopId);
            Integer destination = destinationIndex.get(toStopId);
            return source == null || destination == null ? null : matrix.durationSeconds(source, destination);
        }

        Double distance(String fromStopId, String toStopId) {
            Integer source = sourceIndex.get(fromStopId);
            Integer destination = destinationIndex.get(toStopId);
            return source == null || destination == null ? null : matrix.distanceMeters(source, destination);
        }
    }
}


