package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class DecisionEffortPolicyTest {

    @Test
    void stageDefaultsUseMediumForHeavyStagesAndLowForLightStages() {
        assertEquals(DecisionEffort.MEDIUM, DecisionStageName.PAIR_BUNDLE.requestedEffort());
        assertEquals(DecisionEffort.MEDIUM, DecisionStageName.ROUTE_GENERATION.requestedEffort());
        assertEquals(DecisionEffort.MEDIUM, DecisionStageName.ROUTE_CRITIQUE.requestedEffort());
        assertEquals(DecisionEffort.MEDIUM, DecisionStageName.SCENARIO.requestedEffort());
        assertEquals(DecisionEffort.MEDIUM, DecisionStageName.FINAL_SELECTION.requestedEffort());
        assertEquals(DecisionEffort.LOW, DecisionStageName.ANCHOR.requestedEffort());
        assertEquals(DecisionEffort.LOW, DecisionStageName.DRIVER.requestedEffort());
        assertEquals(DecisionEffort.LOW, DecisionStageName.OBSERVATION_PACK.requestedEffort());
        assertEquals(DecisionEffort.LOW, DecisionStageName.SAFETY_EXECUTE.requestedEffort());
    }

    @Test
    void dynamicPolicyDoesNotEscalateMediumHeavyStageToHighUnderLargeCandidateSet() {
        DecisionEffortPolicy policy = new DecisionEffortPolicy(RouteChainDispatchV2Properties.defaults().getDecision());

        DecisionEffortPolicy.EffortDecision decision = policy.select(input(
                DecisionStageName.PAIR_BUNDLE,
                Map.of("llmLatencyPressureMs", 1200),
                Map.of("topIds", List.of("a", "b", "c", "d", "e", "f", "g", "h", "i"))));

        assertEquals(DecisionEffort.MEDIUM, decision.requestedEffort());
        assertFalse(decision.qualityFlags().contains("effort-escalated"));
    }

    @Test
    void dynamicPolicyKeepsLightStageLowUnderLatencyPressure() {
        DecisionEffortPolicy policy = new DecisionEffortPolicy(RouteChainDispatchV2Properties.defaults().getDecision());

        DecisionEffortPolicy.EffortDecision decision = policy.select(input(
                DecisionStageName.DRIVER,
                Map.of("llmLatencyPressureMs", 1200),
                Map.of("topIds", List.of("driver-1", "driver-2", "driver-3"))));

        assertEquals(DecisionEffort.LOW, decision.requestedEffort());
    }

    private DecisionStageInputV1 input(DecisionStageName stageName,
                                       Map<String, Object> dispatchContext,
                                       Map<String, Object> candidateSet) {
        return new DecisionStageInputV1(
                "stage-input-v1",
                "trace-1",
                "run-1",
                "tick-1",
                stageName,
                dispatchContext,
                candidateSet,
                Map.of(),
                Map.of(),
                Map.of(),
                Map.of(),
                Map.of(),
                Map.of(),
                Map.of(),
                Map.of(),
                List.of());
    }
}