package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DecisionBrainResolverTest {

    @Test
    void defaultModeUsesLegacyWithoutLlm() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        DecisionBrainResolver resolver = new DecisionBrainResolver(
                properties,
                new LegacyMlBrain(),
                new LlmBrain(
                        new LlmStageScheduler(new NineRouterResponsesClient(properties.getDecision().getLlm()), properties.getDecision(), new DecisionStageLogger(properties), new NoOpDecisionSessionStore()),
                        properties.getDecision().getLlm(),
                        new LegacyMlBrain(),
                        new DecisionStageLogger(properties),
                        new ContextToolRegistry()),
                new StudentBrain(new LegacyMlBrain()));

        ResolvedDecisionBrain resolved = resolver.resolve();

        assertEquals(DecisionBrainType.LEGACY, resolved.requestedType());
        assertEquals(DecisionBrainType.LEGACY, resolved.appliedType());
        assertFalse(resolved.fallbackUsed());
        assertEquals(DecisionRuntimeMode.LEGACY, resolved.runtimeMode());
        assertFalse(resolved.shouldEvaluateWithLlm(DecisionStageName.PAIR_BUNDLE));
    }

    @Test
    void llmAuthoritativeModeIsDisabledByPolicy() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().setMode("llm-authoritative");
        properties.getDecision().getLlm().setApiKeyEnv("PATH");
        DecisionBrainResolver resolver = new DecisionBrainResolver(
                properties,
                new LegacyMlBrain(),
                new LlmBrain(
                        new LlmStageScheduler(new NineRouterResponsesClient(properties.getDecision().getLlm()), properties.getDecision(), new DecisionStageLogger(properties), new NoOpDecisionSessionStore()),
                        properties.getDecision().getLlm(),
                        new LegacyMlBrain(),
                        new DecisionStageLogger(properties),
                        new ContextToolRegistry()),
                new StudentBrain(new LegacyMlBrain()));

        ResolvedDecisionBrain resolved = resolver.resolve();

        assertEquals(DecisionBrainType.LLM, resolved.requestedType());
        assertEquals(DecisionBrainType.LEGACY, resolved.appliedType());
        assertEquals(DecisionRuntimeMode.LLM_AUTHORITATIVE, resolved.runtimeMode());
        assertTrue(resolved.fallbackUsed());
        assertEquals("llm-disabled-by-policy", resolved.fallbackReason());
        assertFalse(resolved.shouldEvaluateWithLlm(DecisionStageName.PAIR_BUNDLE));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.PAIR_BUNDLE));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.DRIVER));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.ROUTE_CRITIQUE));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.SCENARIO));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.FINAL_SELECTION));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.ROUTE_GENERATION));
    }

    @Test
    void llmShadowModeIsDisabledByPolicy() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().setMode("llm-shadow");
        properties.getDecision().getLlm().setApiKeyEnv("PATH");
        DecisionBrainResolver resolver = new DecisionBrainResolver(
                properties,
                new LegacyMlBrain(),
                new LlmBrain(
                        new LlmStageScheduler(new NineRouterResponsesClient(properties.getDecision().getLlm()), properties.getDecision(), new DecisionStageLogger(properties), new NoOpDecisionSessionStore()),
                        properties.getDecision().getLlm(),
                        new LegacyMlBrain(),
                        new DecisionStageLogger(properties),
                        new ContextToolRegistry()),
                new StudentBrain(new LegacyMlBrain()));

        ResolvedDecisionBrain resolved = resolver.resolve();

        assertEquals(DecisionBrainType.LLM, resolved.requestedType());
        assertEquals(DecisionBrainType.LEGACY, resolved.appliedType());
        assertEquals(DecisionRuntimeMode.LLM_SHADOW, resolved.runtimeMode());
        assertTrue(resolved.fallbackUsed());
        assertEquals("llm-disabled-by-policy", resolved.fallbackReason());
        assertFalse(resolved.shouldEvaluateWithLlm(DecisionStageName.PAIR_BUNDLE));
        assertFalse(resolved.shouldEvaluateWithLlm(DecisionStageName.DRIVER));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.PAIR_BUNDLE));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.FINAL_SELECTION));
    }
}
