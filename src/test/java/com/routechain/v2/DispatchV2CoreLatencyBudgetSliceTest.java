package com.routechain.v2;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.feedback.DecisionLogRecord;
import com.routechain.v2.feedback.DecisionLogService;
import com.routechain.v2.feedback.DispatchReplayComparator;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchV2CoreLatencyBudgetSliceTest {

    @Test
    void resultExposesTwelveOrderedStageLatenciesAndDecisionLogCopiesThem() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        TestDispatchV2Factory.TestDispatchRuntimeHarness harness = TestDispatchV2Factory.harness(properties);

        DispatchV2Result result = harness.core().dispatch(TestDispatchV2Factory.requestWithOrdersAndDriver());
        DecisionLogService decisionLogService = harness.decisionLogService();
        DecisionLogRecord decisionLogRecord = decisionLogService.latest();

        assertEquals(12, result.stageLatencies().size());
        assertEquals(result.decisionStages(), result.stageLatencies().stream().map(DispatchStageLatency::stageName).toList());
        assertTrue(result.latencyBudgetSummary().totalDispatchLatencyMs() >= 0L);
        assertEquals(properties.getPerformance().getTotalDispatchBudget().toMillis(), result.latencyBudgetSummary().totalDispatchBudgetMs());
        assertEquals(result.stageLatencies(), decisionLogRecord.stageLatencies());
        assertEquals(result.latencyBudgetSummary(), decisionLogRecord.latencyBudgetSummary());
    }

    @Test
    void tinyBudgetsMarkBreachesWithoutChangingRuntimeShapeAndOnlyDegradeWhenEnabled() {
        RouteChainDispatchV2Properties observeOnlyProperties = RouteChainDispatchV2Properties.defaults();
        observeOnlyProperties.getPerformance().getStageBudgets().replaceAll((stageName, ignored) -> Duration.ofMillis(1));
        observeOnlyProperties.getPerformance().setTotalDispatchBudget(Duration.ofMillis(1));
        DispatchV2Result observeOnlyResult = TestDispatchV2Factory.core(observeOnlyProperties)
                .dispatch(TestDispatchV2Factory.requestWithOrdersAndDriver());

        assertEquals(12, observeOnlyResult.decisionStages().size());
        assertTrue(observeOnlyResult.stageLatencies().stream().anyMatch(DispatchStageLatency::budgetBreached));
        assertTrue(observeOnlyResult.latencyBudgetSummary().totalBudgetBreached());
        assertFalse(observeOnlyResult.degradeReasons().stream().anyMatch(reason -> reason.startsWith("dispatch-stage-budget-breached:")));
        assertFalse(observeOnlyResult.degradeReasons().contains("dispatch-total-budget-breached"));

        RouteChainDispatchV2Properties enforcedProperties = RouteChainDispatchV2Properties.defaults();
        enforcedProperties.getPerformance().setBudgetEnforcementEnabled(true);
        enforcedProperties.getPerformance().getStageBudgets().replaceAll((stageName, ignored) -> Duration.ofMillis(1));
        enforcedProperties.getPerformance().setTotalDispatchBudget(Duration.ofMillis(1));
        DispatchV2Result enforcedResult = TestDispatchV2Factory.core(enforcedProperties)
                .dispatch(TestDispatchV2Factory.requestWithOrdersAndDriver());

        assertEquals(12, enforcedResult.decisionStages().size());
        assertTrue(enforcedResult.degradeReasons().stream().anyMatch(reason -> reason.startsWith("dispatch-stage-budget-breached:")));
        assertTrue(enforcedResult.degradeReasons().contains("dispatch-total-budget-breached"));
    }

    @Test
    void replayIgnoresLatencyTelemetryOnlyDifferences() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        DispatchV2Result result = TestDispatchV2Factory.core(properties)
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
                List.of(new DispatchStageLatency("dispatch-stage-latency/v1", "eta/context", 999L, 1L, true, false, 0L)),
                new DispatchLatencyBudgetSummary("dispatch-latency-budget-summary/v1", 999L, 1L, true, List.of("eta/context"), 0L),
                result.mlStageMetadata(),
                result.mlStageMetadata().stream()
                        .map(com.routechain.v2.feedback.MlContributionTrace::from)
                        .toList(),
                result.liveStageMetadata(),
                result.globalSelectionResult().selectedProposals().stream().map(selected -> selected.proposalId()).toList(),
                result.assignments().stream().map(assignment -> assignment.assignmentId()).toList());

        assertTrue(new DispatchReplayComparator().compare(reference, null, result).matched());
    }
}
