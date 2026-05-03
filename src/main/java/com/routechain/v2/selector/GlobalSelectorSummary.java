package com.routechain.v2.selector;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record GlobalSelectorSummary(
        String schemaVersion,
        int candidateCount,
        int feasibleCandidateCount,
        int conflictEdgeCount,
        int selectedCount,
        SelectionSolverMode solverMode,
        int poolInputCount,
        int poolReducedCount,
        int poolRejectedCount,
        boolean selectorTimedOut,
        String selectorFallbackLevel,
        boolean acceptanceGatePassed,
        List<String> acceptanceGateRejectedReasons,
        int selectorMaxPoolSize,
        boolean selectorPoolCapApplied,
        double selectorPoolCapObjectiveLoss,
        List<String> degradeReasons) implements SchemaVersioned {

    public GlobalSelectorSummary(
            String schemaVersion,
            int candidateCount,
            int feasibleCandidateCount,
            int conflictEdgeCount,
            int selectedCount,
            SelectionSolverMode solverMode,
            List<String> degradeReasons) {
        this(schemaVersion,
                candidateCount,
                feasibleCandidateCount,
                conflictEdgeCount,
                selectedCount,
                solverMode,
                candidateCount,
                candidateCount,
                0,
                false,
                "NONE",
                true,
                List.of(),
                candidateCount,
                false,
                0.0,
                degradeReasons);
    }

    public GlobalSelectorSummary(
            String schemaVersion,
            int candidateCount,
            int feasibleCandidateCount,
            int conflictEdgeCount,
            int selectedCount,
            SelectionSolverMode solverMode,
            int poolInputCount,
            int poolReducedCount,
            int poolRejectedCount,
            boolean selectorTimedOut,
            String selectorFallbackLevel,
            boolean acceptanceGatePassed,
            List<String> acceptanceGateRejectedReasons,
            List<String> degradeReasons) {
        this(schemaVersion,
                candidateCount,
                feasibleCandidateCount,
                conflictEdgeCount,
                selectedCount,
                solverMode,
                poolInputCount,
                poolReducedCount,
                poolRejectedCount,
                selectorTimedOut,
                selectorFallbackLevel,
                acceptanceGatePassed,
                acceptanceGateRejectedReasons,
                poolReducedCount,
                false,
                0.0,
                degradeReasons);
    }

    public GlobalSelectorSummary {
        selectorFallbackLevel = selectorFallbackLevel == null ? "NONE" : selectorFallbackLevel;
        acceptanceGateRejectedReasons = acceptanceGateRejectedReasons == null ? List.of() : List.copyOf(acceptanceGateRejectedReasons);
        selectorMaxPoolSize = Math.max(0, selectorMaxPoolSize);
        selectorPoolCapObjectiveLoss = Double.isFinite(selectorPoolCapObjectiveLoss) ? selectorPoolCapObjectiveLoss : 0.0;
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }

    public static GlobalSelectorSummary empty() {
        return new GlobalSelectorSummary(
                "global-selector-summary/v1",
                0,
                0,
                0,
                0,
                SelectionSolverMode.GREEDY_REPAIR,
                0,
                0,
                0,
                false,
                "NONE",
                true,
                List.of(),
                0,
                false,
                0.0,
                List.of());
    }
}
