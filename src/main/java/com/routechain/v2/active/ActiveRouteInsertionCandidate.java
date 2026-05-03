package com.routechain.v2.active;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record ActiveRouteInsertionCandidate(
        String schemaVersion,
        String candidateId,
        String routeId,
        String driverId,
        String insertedOrderId,
        int pickupInsertionIndex,
        List<String> newStopOrder,
        double projectedPickupEtaMinutes,
        double projectedCompletionEtaMinutes,
        double incrementalCompletionEtaMinutes,
        double freshnessRisk,
        double churnRisk,
        double routeShapeRisk,
        double score,
        boolean feasible,
        List<String> reasons,
        List<String> degradeReasons) implements SchemaVersioned {

    public ActiveRouteInsertionCandidate {
        newStopOrder = newStopOrder == null ? List.of() : List.copyOf(newStopOrder);
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }
}
