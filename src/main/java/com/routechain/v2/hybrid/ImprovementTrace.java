package com.routechain.v2.hybrid;

import java.util.List;

public record ImprovementTrace(
        CandidateSource seedSource,
        double startKm,
        double afterPermutationKm,
        double afterLocalSearchKm,
        double finalKm,
        long lateOrders,
        boolean objectiveImproved,
        int acceptedMoves,
        int rejectedMoves,
        List<String> reasons,
        List<MoveEvaluationTrace> moveTraces) {

    public ImprovementTrace {
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
        moveTraces = moveTraces == null ? List.of() : List.copyOf(moveTraces);
    }
}
