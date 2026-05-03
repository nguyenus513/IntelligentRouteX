package com.routechain.v2.selector;

import java.util.List;
import java.util.Map;

public record SelectorPoolReductionResult(
        List<SelectorCandidateEnvelope> retainedCandidates,
        int rejectedCandidateCount,
        List<String> reasons,
        int checkedCandidateCount,
        int feasibleCandidateCount,
        Map<String, Integer> violationCountsByCode,
        int maxPoolSize,
        boolean poolCapApplied,
        double retainedBestObjectiveUtility,
        double feasibleBestObjectiveUtility) {

    public SelectorPoolReductionResult {
        retainedCandidates = retainedCandidates == null ? List.of() : List.copyOf(retainedCandidates);
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
        violationCountsByCode = violationCountsByCode == null ? Map.of() : Map.copyOf(violationCountsByCode);
        maxPoolSize = Math.max(0, maxPoolSize);
    }

    public SelectorPoolReductionResult(
            List<SelectorCandidateEnvelope> retainedCandidates,
            int rejectedCandidateCount,
            List<String> reasons,
            int checkedCandidateCount,
            int feasibleCandidateCount,
            Map<String, Integer> violationCountsByCode) {
        this(retainedCandidates,
                rejectedCandidateCount,
                reasons,
                checkedCandidateCount,
                feasibleCandidateCount,
                violationCountsByCode,
                retainedCandidates == null ? 0 : retainedCandidates.size(),
                false,
                bestObjective(retainedCandidates),
                bestObjective(retainedCandidates));
    }

    public SelectorPoolReductionResult(
            List<SelectorCandidateEnvelope> retainedCandidates,
            int rejectedCandidateCount,
            List<String> reasons) {
        this(retainedCandidates, rejectedCandidateCount, reasons, retainedCandidates == null ? 0 : retainedCandidates.size(), retainedCandidates == null ? 0 : retainedCandidates.size(), Map.of());
    }

    private static double bestObjective(List<SelectorCandidateEnvelope> candidates) {
        if (candidates == null || candidates.isEmpty()) {
            return 0.0;
        }
        return candidates.stream()
                .map(SelectorCandidateEnvelope::candidate)
                .mapToDouble(SelectorCandidateRanking::objectiveUtility)
                .max()
                .orElse(0.0);
    }
}
