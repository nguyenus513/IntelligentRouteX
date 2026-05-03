package com.routechain.v2.active;

import com.routechain.domain.GeoPoint;
import com.routechain.v2.SchemaVersioned;
import com.routechain.v2.executor.DispatchAssignment;

import java.time.Instant;
import java.util.List;

public record ActiveRouteState(
        String schemaVersion,
        String routeId,
        String driverId,
        GeoPoint currentLocation,
        List<String> assignedOrderIds,
        List<String> remainingStopOrder,
        Instant startedAt,
        double elapsedRouteMinutes,
        double projectedCompletionEtaMinutes,
        double routeStabilityScore,
        List<String> reasons) implements SchemaVersioned {

    public ActiveRouteState {
        assignedOrderIds = assignedOrderIds == null ? List.of() : List.copyOf(assignedOrderIds);
        remainingStopOrder = remainingStopOrder == null ? List.of() : List.copyOf(remainingStopOrder);
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
    }

    public static ActiveRouteState fromAssignment(DispatchAssignment assignment,
                                                  GeoPoint currentLocation,
                                                  Instant decisionTime) {
        return new ActiveRouteState(
                "active-route-state/v1",
                assignment.assignmentId(),
                assignment.driverId(),
                currentLocation,
                assignment.orderIds(),
                assignment.stopOrder(),
                decisionTime,
                0.0,
                assignment.projectedCompletionEtaMinutes(),
                1.0,
                List.of("active-route-from-dispatch-assignment"));
    }
}
