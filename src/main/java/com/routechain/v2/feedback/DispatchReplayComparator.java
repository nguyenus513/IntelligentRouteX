package com.routechain.v2.feedback;

import com.routechain.v2.DispatchV2Result;

import java.util.ArrayList;
import java.util.List;

public final class DispatchReplayComparator {

    public ReplayComparisonResult compare(DecisionLogRecord referenceDecisionLog,
                                          DispatchRuntimeSnapshot referenceSnapshot,
                                          DispatchV2Result replayResult) {
        List<String> mismatchReasons = new ArrayList<>();

        List<String> expectedDecisionStages = referenceDecisionLog != null
                ? referenceDecisionLog.decisionStages()
                : referenceSnapshot != null ? referenceSnapshot.decisionStages() : null;
        List<String> expectedSelectedProposalIds = referenceDecisionLog != null
                ? referenceDecisionLog.selectedProposalIds()
                : referenceSnapshot != null ? referenceSnapshot.selectedProposalIds() : null;
        List<String> expectedExecutedAssignmentIds = referenceDecisionLog != null
                ? referenceDecisionLog.executedAssignmentIds()
                : referenceSnapshot != null ? referenceSnapshot.executedAssignmentIds() : null;
        Integer expectedSelectedCount = referenceDecisionLog != null
                ? Integer.valueOf(referenceDecisionLog.globalSelectorSummary().selectedCount())
                : expectedSelectedProposalIds != null ? Integer.valueOf(expectedSelectedProposalIds.size()) : null;
        Integer expectedExecutedAssignmentCount = referenceDecisionLog != null
                ? Integer.valueOf(referenceDecisionLog.dispatchExecutionSummary().executedAssignmentCount())
                : expectedExecutedAssignmentIds != null ? Integer.valueOf(expectedExecutedAssignmentIds.size()) : null;

        if (expectedDecisionStages == null && expectedSelectedProposalIds == null && expectedExecutedAssignmentIds == null) {
            mismatchReasons.add("replay-reference-missing");
        }
        if (expectedDecisionStages != null && !expectedDecisionStages.equals(replayResult.decisionStages())) {
            mismatchReasons.add("decision-stages-mismatch");
        }
        List<String> replaySelectedProposalIds = replayResult.globalSelectionResult().selectedProposals().stream()
                .map(selectedProposal -> selectedProposal.proposalId())
                .toList();
        List<String> replayExecutedAssignmentIds = replayResult.assignments().stream()
                .map(assignment -> assignment.assignmentId())
                .toList();
        if (expectedSelectedCount != null && expectedSelectedCount != replayResult.globalSelectionResult().selectedCount()) {
            mismatchReasons.add("selected-count-mismatch");
        }
        if (expectedExecutedAssignmentCount != null
                && expectedExecutedAssignmentCount != replayResult.dispatchExecutionSummary().executedAssignmentCount()) {
            mismatchReasons.add("executed-assignment-count-mismatch");
        }
        if (referenceDecisionLog != null) {
            ReplayMlMetadataComparator.compare(referenceDecisionLog.mlStageMetadata(), replayResult.mlStageMetadata(), mismatchReasons);
            ReplayLiveMetadataComparator.compare(referenceDecisionLog.liveStageMetadata(), replayResult.liveStageMetadata(), mismatchReasons);
        }

        return new ReplayComparisonResult(
                "replay-comparison-result/v1",
                mismatchReasons.isEmpty(),
                List.copyOf(mismatchReasons));
    }
}
