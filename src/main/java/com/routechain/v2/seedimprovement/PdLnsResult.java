package com.routechain.v2.seedimprovement;

import com.routechain.v2.mlproof.MlParticipationDiagnostics;

import java.util.List;

public record PdLnsResult(
        boolean applied,
        PdSeedState baseSeed,
        PdSeedState finalSeed,
        PdEvaluation baseEvaluation,
        PdEvaluation finalEvaluation,
        int rounds,
        int evaluatedOrders,
        int evaluatedInsertions,
        int feasibleInsertions,
        int acceptedMutations,
        List<PdLnsTrace> traces,
        MlParticipationDiagnostics mlParticipationDiagnostics) {

    public PdLnsResult {
        traces = traces == null ? List.of() : List.copyOf(traces);
        mlParticipationDiagnostics = mlParticipationDiagnostics == null ? MlParticipationDiagnostics.empty() : mlParticipationDiagnostics;
    }

    public PdLnsResult(boolean applied,
                       PdSeedState baseSeed,
                       PdSeedState finalSeed,
                       PdEvaluation baseEvaluation,
                       PdEvaluation finalEvaluation,
                       int rounds,
                       int evaluatedOrders,
                       int evaluatedInsertions,
                       int feasibleInsertions,
                       int acceptedMutations,
                       List<PdLnsTrace> traces) {
        this(applied, baseSeed, finalSeed, baseEvaluation, finalEvaluation, rounds, evaluatedOrders, evaluatedInsertions, feasibleInsertions, acceptedMutations, traces, MlParticipationDiagnostics.empty());
    }

    public double gainKm() {
        return baseEvaluation == null || finalEvaluation == null ? 0.0 : Math.round((baseEvaluation.distanceKm() - finalEvaluation.distanceKm()) * 10.0) / 10.0;
    }
}
