package com.routechain.v2.feedback;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.TestDispatchV2Factory;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReplayComparisonResultTest {

    @Test
    void identicalReplayPassesCleanly() {
        DispatchV2Result result = TestDispatchV2Factory.core(RouteChainDispatchV2Properties.defaults())
                .dispatch(TestDispatchV2Factory.requestWithOrdersAndDriver());
        DecisionLogRecord reference = new DecisionLogAssembler()
                .assemble(TestDispatchV2Factory.requestWithOrdersAndDriver(), result);

        ReplayComparisonResult comparisonResult = new DispatchReplayComparator().compare(reference, null, result);

        assertTrue(comparisonResult.matched());
        assertTrue(comparisonResult.mismatchReasons().isEmpty());
    }

    @Test
    void mismatchedIdsProduceSpecificReasons() {
        DispatchV2Result result = TestDispatchV2Factory.core(RouteChainDispatchV2Properties.defaults())
                .dispatch(TestDispatchV2Factory.requestWithOrdersAndDriver());
        DecisionLogRecord reference = new DecisionLogRecord(
                "decision-log-record/v1",
                result.traceId(),
                TestDispatchV2Factory.requestWithOrdersAndDriver().decisionTime(),
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
                List.of("other-proposal"),
                List.of("other-assignment"));

        ReplayComparisonResult comparisonResult = new DispatchReplayComparator().compare(reference, null, result);

        assertFalse(comparisonResult.matched());
        assertTrue(comparisonResult.mismatchReasons().contains("selected-proposal-ids-mismatch"));
        assertTrue(comparisonResult.mismatchReasons().contains("executed-assignment-ids-mismatch"));
    }
}
