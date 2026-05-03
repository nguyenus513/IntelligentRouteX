package com.routechain.v2.selector;

import java.util.List;

public record AcceptanceGateResult(
        boolean accepted,
        double incumbentObjective,
        double candidateObjective,
        double improvementPct,
        List<String> rejectedReasons) {

    public AcceptanceGateResult {
        rejectedReasons = rejectedReasons == null ? List.of() : List.copyOf(rejectedReasons);
    }
}
