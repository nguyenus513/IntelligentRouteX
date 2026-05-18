package com.routechain.v2.seedimprovement;

import java.util.List;

public record PdOperatorResult(
        PdSeedState seed,
        PdEvaluation evaluation,
        String operator,
        String orderIds,
        int evaluatedCandidates,
        int feasibleCandidates) {

    public static PdOperatorResult empty(String operator) {
        return new PdOperatorResult(null, null, operator, "", 0, 0);
    }

    public static String ids(List<String> orderIds) {
        return orderIds == null ? "" : String.join(",", orderIds);
    }
}
