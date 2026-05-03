package com.routechain.v2.selector;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record GlobalSelectionResult(
        String schemaVersion,
        List<SelectedProposal> selectedProposals,
        int retainedCandidateCount,
        int selectedCount,
        SelectionSolverMode solverMode,
        double objectiveValue,
        int selectorPoolInputCount,
        int selectorPoolReducedCount,
        int selectorFeasibleCount,
        int selectorRejectedCount,
        boolean selectorTimedOut,
        String selectorFallbackLevel,
        boolean acceptanceGatePassed,
        List<String> acceptanceGateRejectedReasons,
        int selectorMaxPoolSize,
        boolean selectorPoolCapApplied,
        double selectorRetainedBestObjectiveUtility,
        double selectorFeasibleBestObjectiveUtility,
        List<String> degradeReasons) implements SchemaVersioned {

    public GlobalSelectionResult(
            String schemaVersion,
            List<SelectedProposal> selectedProposals,
            int retainedCandidateCount,
            int selectedCount,
            SelectionSolverMode solverMode,
            double objectiveValue,
            List<String> degradeReasons) {
        this(schemaVersion,
                selectedProposals,
                retainedCandidateCount,
                selectedCount,
                solverMode,
                objectiveValue,
                retainedCandidateCount,
                retainedCandidateCount,
                retainedCandidateCount,
                0,
                false,
                "NONE",
                true,
                List.of(),
                retainedCandidateCount,
                false,
                objectiveValue,
                objectiveValue,
                degradeReasons);
    }

    public GlobalSelectionResult(
            String schemaVersion,
            List<SelectedProposal> selectedProposals,
            int retainedCandidateCount,
            int selectedCount,
            SelectionSolverMode solverMode,
            double objectiveValue,
            int selectorPoolInputCount,
            int selectorPoolReducedCount,
            int selectorFeasibleCount,
            int selectorRejectedCount,
            boolean selectorTimedOut,
            String selectorFallbackLevel,
            boolean acceptanceGatePassed,
            List<String> acceptanceGateRejectedReasons,
            List<String> degradeReasons) {
        this(schemaVersion,
                selectedProposals,
                retainedCandidateCount,
                selectedCount,
                solverMode,
                objectiveValue,
                selectorPoolInputCount,
                selectorPoolReducedCount,
                selectorFeasibleCount,
                selectorRejectedCount,
                selectorTimedOut,
                selectorFallbackLevel,
                acceptanceGatePassed,
                acceptanceGateRejectedReasons,
                selectorPoolReducedCount,
                false,
                objectiveValue,
                objectiveValue,
                degradeReasons);
    }

    public GlobalSelectionResult {
        selectedProposals = selectedProposals == null ? List.of() : List.copyOf(selectedProposals);
        selectorFallbackLevel = selectorFallbackLevel == null ? "NONE" : selectorFallbackLevel;
        acceptanceGateRejectedReasons = acceptanceGateRejectedReasons == null ? List.of() : List.copyOf(acceptanceGateRejectedReasons);
        selectorMaxPoolSize = Math.max(0, selectorMaxPoolSize);
        selectorRetainedBestObjectiveUtility = Double.isFinite(selectorRetainedBestObjectiveUtility) ? selectorRetainedBestObjectiveUtility : 0.0;
        selectorFeasibleBestObjectiveUtility = Double.isFinite(selectorFeasibleBestObjectiveUtility) ? selectorFeasibleBestObjectiveUtility : 0.0;
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }

    public double selectorPoolCapObjectiveLoss() {
        return Math.max(0.0, selectorFeasibleBestObjectiveUtility - selectorRetainedBestObjectiveUtility);
    }

    public static GlobalSelectionResult empty() {
        return new GlobalSelectionResult(
                "global-selection-result/v1",
                List.of(),
                0,
                0,
                SelectionSolverMode.GREEDY_REPAIR,
                0.0,
                0,
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
                0.0,
                List.of());
    }
}
