package com.routechain.v2.mlproof;

public record MlWorkerInvocationTrace(
        String workerName,
        boolean called,
        String modelVersion,
        int inferenceCount,
        int candidateCount,
        boolean outputUsed,
        int affectedDecisionCount,
        int acceptedCandidateCount,
        String reason) {
}
