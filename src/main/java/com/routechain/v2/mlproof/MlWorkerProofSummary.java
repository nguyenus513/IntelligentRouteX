package com.routechain.v2.mlproof;

import java.util.List;
import java.util.Map;

public record MlWorkerProofSummary(
        boolean blockPresent,
        boolean anyWorkerCalled,
        boolean workerContributionProven,
        String verdict,
        Map<String, MlWorkerInvocationTrace> workers,
        List<MlWorkerDecisionImpact> impacts) {

    public MlWorkerProofSummary {
        workers = workers == null ? Map.of() : Map.copyOf(workers);
        impacts = impacts == null ? List.of() : List.copyOf(impacts);
    }
}
