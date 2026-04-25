package com.routechain.v2.routing;

import java.util.List;
import java.util.Map;

public record RouteSequence(
        String schemaVersion,
        List<PickupDeliveryStop> stops,
        double totalDurationSeconds,
        double totalDistanceMeters,
        double averageDetourRatio,
        double maxDetourRatio,
        double score,
        boolean feasible,
        List<String> rejectReasons,
        Map<String, Double> detourRatioByOrder) {

    public RouteSequence {
        stops = stops == null ? List.of() : List.copyOf(stops);
        rejectReasons = rejectReasons == null ? List.of() : List.copyOf(rejectReasons);
        detourRatioByOrder = detourRatioByOrder == null ? Map.of() : Map.copyOf(detourRatioByOrder);
    }

    public List<String> stopIds() {
        return stops.stream().map(PickupDeliveryStop::stopId).toList();
    }
}
