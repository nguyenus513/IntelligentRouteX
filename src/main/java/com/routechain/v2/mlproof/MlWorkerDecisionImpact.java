package com.routechain.v2.mlproof;

public record MlWorkerDecisionImpact(
        String workerName,
        String decisionId,
        String affectedOperator,
        boolean outputUsed,
        boolean affectedDecision,
        boolean acceptedCandidate,
        double gainKm) {
}
