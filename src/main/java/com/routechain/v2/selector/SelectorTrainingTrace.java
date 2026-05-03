package com.routechain.v2.selector;

import com.routechain.v2.SchemaVersioned;
import com.routechain.v2.route.RouteProposalSource;

import java.util.List;

public record SelectorTrainingTrace(
        String schemaVersion,
        String traceId,
        String proposalId,
        RouteProposalSource source,
        String driverId,
        List<String> orderIds,
        double selectionScore,
        double robustUtility,
        double routeValue,
        boolean feasible,
        boolean selected,
        List<String> reasons,
        List<String> degradeReasons) implements SchemaVersioned {

    public SelectorTrainingTrace {
        orderIds = orderIds == null ? List.of() : List.copyOf(orderIds);
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }
}
