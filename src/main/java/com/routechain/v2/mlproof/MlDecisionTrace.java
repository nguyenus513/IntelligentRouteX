package com.routechain.v2.mlproof;

import java.util.List;

public record MlDecisionTrace(
        String decisionId,
        String decisionType,
        String operator,
        int candidateCountBeforeMl,
        int candidateCountAfterMl,
        List<String> selectedOrderIds,
        String selectionSource,
        int mlRank,
        int heuristicRank,
        boolean accepted,
        double gainKm) {

    public MlDecisionTrace {
        selectedOrderIds = selectedOrderIds == null ? List.of() : List.copyOf(selectedOrderIds);
    }
}
