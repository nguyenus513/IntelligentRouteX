package com.routechain.v2.mlproof;

import java.util.List;
import java.util.Map;

public record MlParticipationDiagnostics(
        int decisionTraceCount,
        int rankedMutationCount,
        int acceptedMutationFromMlTopK,
        int rewardUpdates,
        Map<String, Object> policyLayer,
        Map<String, MlWorkerInvocationTrace> workerInvocations,
        List<MlDecisionTrace> decisions) {

    public MlParticipationDiagnostics {
        policyLayer = policyLayer == null ? Map.of() : Map.copyOf(policyLayer);
        workerInvocations = workerInvocations == null ? Map.of() : Map.copyOf(workerInvocations);
        decisions = decisions == null ? List.of() : List.copyOf(decisions);
    }

    public static MlParticipationDiagnostics empty() {
        return new MlParticipationDiagnostics(0, 0, 0, 0, Map.of(), Map.of(), List.of());
    }
}
