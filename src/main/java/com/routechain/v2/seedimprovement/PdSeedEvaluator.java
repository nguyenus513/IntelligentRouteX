package com.routechain.v2.seedimprovement;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class PdSeedEvaluator {
    private static final double SPEED_KMPH = 22.0;

    public PdValidationResult evaluate(PdSeedState seed) {
        PdEvaluation evaluation = evaluateSeed(seed);
        int missing = evaluation.missingStopViolations();
        return new PdValidationResult(
                evaluation.valid(),
                evaluation.pickupDropoffViolations(),
                evaluation.capacityViolations(),
                missing,
                missing,
                evaluation.duplicateStopViolations(),
                evaluation.assignedCount(),
                evaluation.lateCount(),
                evaluation.distanceKm(),
                evaluation.rejectReason().isBlank() ? List.of() : List.of(evaluation.rejectReason()));
    }

    public PdEvaluation evaluateSeed(PdSeedState seed) {
        if (seed == null) {
            return new PdEvaluation(false, 0, 0, 0.0, 0.0, 0.0, 0, 0, 0, 0, "missing-seed");
        }
        Map<String, Integer> pickups = new HashMap<>();
        Map<String, Integer> dropoffs = new HashMap<>();
        Set<String> completedOrders = new HashSet<>();
        Set<String> seenStops = new HashSet<>();
        List<String> reasons = new ArrayList<>();
        int precedenceViolations = 0;
        int capacityViolations = 0;
        int duplicateStop = 0;
        int lateCount = 0;
        double totalLateness = 0.0;
        double totalKm = 0.0;
        double totalMinutes = 0.0;
        for (PdRouteState route : seed.routes()) {
            Set<String> pickedOnRoute = new HashSet<>();
            int load = 0;
            double minutes = 0.0;
            double previousLat = route.startLat();
            double previousLng = route.startLng();
            for (PdStop stop : route.stops()) {
                String stopKey = stop.type() + ":" + stop.orderId();
                if (!seenStops.add(stopKey)) {
                    duplicateStop++;
                    reasons.add("duplicate-stop:" + stopKey);
                }
                double legKm = haversineKm(previousLat, previousLng, stop.lat(), stop.lng());
                totalKm += legKm;
                minutes += legKm / SPEED_KMPH * 60.0 + Math.max(0, stop.serviceMinutes());
                previousLat = stop.lat();
                previousLng = stop.lng();
                if (stop.type() == PdStop.PdStopType.PICKUP) {
                    pickups.merge(stop.orderId(), 1, Integer::sum);
                    pickedOnRoute.add(stop.orderId());
                } else {
                    dropoffs.merge(stop.orderId(), 1, Integer::sum);
                    if (!pickedOnRoute.contains(stop.orderId())) {
                        precedenceViolations++;
                        reasons.add("dropoff-before-pickup:" + stop.orderId());
                    }
                    completedOrders.add(stop.orderId());
                    double lateness = stop.deadlineMinutes() <= 0.0 ? 0.0 : minutes - stop.deadlineMinutes();
                    if (lateness > 0.0) {
                        lateCount++;
                        totalLateness += lateness;
                    }
                }
                load += normalizedLoadDelta(stop);
                if (load < 0 || load > route.capacity()) {
                    capacityViolations++;
                    reasons.add("capacity-violation:" + route.routeId() + ":" + stop.orderId());
                }
            }
            totalMinutes += minutes;
        }
        int missingStops = 0;
        for (String orderId : unionKeys(pickups, dropoffs)) {
            if (pickups.getOrDefault(orderId, 0) != 1) {
                missingStops++;
                reasons.add("missing-or-duplicate-pickup:" + orderId);
            }
            if (dropoffs.getOrDefault(orderId, 0) != 1) {
                missingStops++;
                reasons.add("missing-or-duplicate-dropoff:" + orderId);
            }
        }
        boolean valid = precedenceViolations == 0 && capacityViolations == 0 && missingStops == 0 && duplicateStop == 0;
        return new PdEvaluation(valid, completedOrders.size(), lateCount, round(totalLateness), round(totalKm), round(totalMinutes), precedenceViolations, capacityViolations, duplicateStop, missingStops, String.join(";", reasons));
    }

    private int normalizedLoadDelta(PdStop stop) {
        if (stop.loadDelta() != 0) {
            return stop.loadDelta();
        }
        return stop.type() == PdStop.PdStopType.PICKUP ? 1 : -1;
    }

    private Set<String> unionKeys(Map<String, Integer> left, Map<String, Integer> right) {
        Set<String> keys = new HashSet<>(left.keySet());
        keys.addAll(right.keySet());
        return keys;
    }

    private double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double radius = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
