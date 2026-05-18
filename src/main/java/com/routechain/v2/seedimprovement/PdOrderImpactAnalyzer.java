package com.routechain.v2.seedimprovement;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class PdOrderImpactAnalyzer {
    public List<PdOrderImpact> rankBadOrders(PdSeedState seed) {
        if (seed == null) {
            return List.of();
        }
        List<PdOrderImpact> impacts = new ArrayList<>();
        for (PdRouteState route : seed.routes()) {
            Set<String> orderIds = new HashSet<>();
            route.stops().forEach(stop -> orderIds.add(stop.orderId()));
            double routeDistancePerOrder = orderIds.isEmpty() ? 0.0 : routeDistance(route) / orderIds.size();
            for (String orderId : orderIds) {
                PdStop pickup = findStop(route, orderId, PdStop.PdStopType.PICKUP);
                PdStop dropoff = findStop(route, orderId, PdStop.PdStopType.DROPOFF);
                if (pickup == null || dropoff == null) {
                    continue;
                }
                double detour = detourContribution(route, orderId);
                double spread = haversineKm(pickup.lat(), pickup.lng(), dropoff.lat(), dropoff.lng());
                double score = detour + routeDistancePerOrder * 0.25 + spread * 0.10;
                impacts.add(new PdOrderImpact(orderId, route.routeId(), round(detour), round(spread), round(routeDistancePerOrder), round(score)));
            }
        }
        return impacts.stream()
                .sorted(Comparator.comparingDouble(PdOrderImpact::score).reversed())
                .toList();
    }

    private double detourContribution(PdRouteState route, String orderId) {
        List<PdStop> stops = route.stops();
        double contribution = 0.0;
        for (int index = 0; index < stops.size(); index++) {
            PdStop stop = stops.get(index);
            if (!stop.orderId().equals(orderId)) {
                continue;
            }
            double previousLat = index == 0 ? route.startLat() : stops.get(index - 1).lat();
            double previousLng = index == 0 ? route.startLng() : stops.get(index - 1).lng();
            double nextLat = index + 1 >= stops.size() ? stop.lat() : stops.get(index + 1).lat();
            double nextLng = index + 1 >= stops.size() ? stop.lng() : stops.get(index + 1).lng();
            contribution += haversineKm(previousLat, previousLng, stop.lat(), stop.lng())
                    + haversineKm(stop.lat(), stop.lng(), nextLat, nextLng)
                    - haversineKm(previousLat, previousLng, nextLat, nextLng);
        }
        return Math.max(0.0, contribution);
    }

    private double routeDistance(PdRouteState route) {
        double total = 0.0;
        double previousLat = route.startLat();
        double previousLng = route.startLng();
        for (PdStop stop : route.stops()) {
            total += haversineKm(previousLat, previousLng, stop.lat(), stop.lng());
            previousLat = stop.lat();
            previousLng = stop.lng();
        }
        return total;
    }

    private PdStop findStop(PdRouteState route, String orderId, PdStop.PdStopType type) {
        return route.stops().stream()
                .filter(stop -> stop.orderId().equals(orderId) && stop.type() == type)
                .findFirst()
                .orElse(null);
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
