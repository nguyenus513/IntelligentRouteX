package com.routechain.v2.seedimprovement;

import java.util.List;

public record PdRouteState(
        String routeId,
        String driverId,
        int capacity,
        double startLat,
        double startLng,
        List<PdStop> stops,
        double distanceKm,
        double durationMinutes,
        int lateCount,
        double totalLatenessMinutes) {

    public PdRouteState {
        routeId = routeId == null ? "" : routeId;
        driverId = driverId == null ? "" : driverId;
        capacity = Math.max(0, capacity);
        stops = stops == null ? List.of() : List.copyOf(stops);
    }

    public PdRouteState withStops(List<PdStop> nextStops) {
        return new PdRouteState(routeId, driverId, capacity, startLat, startLng, nextStops, distanceKm, durationMinutes, lateCount, totalLatenessMinutes);
    }
}
