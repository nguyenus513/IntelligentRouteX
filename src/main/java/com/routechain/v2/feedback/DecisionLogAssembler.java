package com.routechain.v2.feedback;

import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;

public final class DecisionLogAssembler {

    public DecisionLogRecord assemble(DispatchV2Request request, DispatchV2Result result) {
        return new DecisionLogRecord(
                "decision-log-record/v1",
                result.traceId(),
                request.decisionTime(),
                result.decisionStages(),
                result.fallbackUsed(),
                result.degradeReasons(),
                result.etaContext(),
                result.pairGraphSummary(),
                result.microClusterSummary(),
                result.bundlePoolSummary(),
                result.pickupAnchorSummary(),
                result.driverShortlistSummary(),
                result.routeProposalSummary(),
                result.scenarioEvaluationSummary(),
                result.globalSelectorSummary(),
                result.dispatchExecutionSummary(),
                result.stageLatencies(),
                result.latencyBudgetSummary(),
                result.mlStageMetadata(),
                result.mlStageMetadata().stream()
                        .map(MlContributionTrace::from)
                        .toList(),
                result.liveStageMetadata(),
                result.globalSelectionResult().selectedProposals().stream()
                        .map(selectedProposal -> selectedProposal.proposalId())
                        .toList(),
                result.assignments().stream()
                        .map(assignment -> assignment.assignmentId())
                        .toList());
    }
}
