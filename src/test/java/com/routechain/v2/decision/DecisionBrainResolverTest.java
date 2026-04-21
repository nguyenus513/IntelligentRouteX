package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DecisionBrainResolverTest {

    @Test
    void fallsBackToLegacyWhenLlmApiKeyIsMissing() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().getLlm().setApiKeyEnv("IRX_TEST_MISSING_KEY");
        DecisionBrainResolver resolver = new DecisionBrainResolver(
                properties,
                new LegacyMlBrain(),
                new LlmBrain(
                        new LlmStageScheduler(new NineRouterResponsesClient(properties.getDecision().getLlm()), properties.getDecision(), new DecisionStageLogger(properties)),
                        properties.getDecision().getLlm(),
                        new LegacyMlBrain(),
                        new DecisionStageLogger(properties),
                        new ContextToolRegistry()),
                new StudentBrain(new LegacyMlBrain()));

        ResolvedDecisionBrain resolved = resolver.resolve();

        assertEquals(DecisionBrainType.LLM, resolved.requestedType());
        assertEquals(DecisionBrainType.LEGACY, resolved.appliedType());
        assertTrue(resolved.fallbackUsed());
        assertEquals("llm-api-key-missing", resolved.fallbackReason());
    }

    @Test
    void llmAuthoritativeModeMarksGuardedPrimaryStagesAsAuthoritative() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().setMode("llm-authoritative");
        properties.getDecision().getLlm().setApiKeyEnv("PATH");
        DecisionBrainResolver resolver = new DecisionBrainResolver(
                properties,
                new LegacyMlBrain(),
                new LlmBrain(
                        new LlmStageScheduler(new NineRouterResponsesClient(properties.getDecision().getLlm()), properties.getDecision(), new DecisionStageLogger(properties)),
                        properties.getDecision().getLlm(),
                        new LegacyMlBrain(),
                        new DecisionStageLogger(properties),
                        new ContextToolRegistry()),
                new StudentBrain(new LegacyMlBrain()));

        ResolvedDecisionBrain resolved = resolver.resolve();

        assertEquals(DecisionRuntimeMode.LLM_AUTHORITATIVE, resolved.runtimeMode());
        assertTrue(resolved.shouldApplyAuthoritatively(DecisionStageName.PAIR_BUNDLE));
        assertTrue(resolved.shouldApplyAuthoritatively(DecisionStageName.DRIVER));
        assertTrue(resolved.shouldApplyAuthoritatively(DecisionStageName.ROUTE_CRITIQUE));
        assertTrue(resolved.shouldApplyAuthoritatively(DecisionStageName.SCENARIO));
        assertTrue(resolved.shouldApplyAuthoritatively(DecisionStageName.FINAL_SELECTION));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.ROUTE_GENERATION));
    }

    @Test
    void llmShadowModeRunsLlmWithoutApplyingAuthority() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().setMode("llm-shadow");
        properties.getDecision().getLlm().setApiKeyEnv("PATH");
        DecisionBrainResolver resolver = new DecisionBrainResolver(
                properties,
                new LegacyMlBrain(),
                new LlmBrain(
                        new LlmStageScheduler(new NineRouterResponsesClient(properties.getDecision().getLlm()), properties.getDecision(), new DecisionStageLogger(properties)),
                        properties.getDecision().getLlm(),
                        new LegacyMlBrain(),
                        new DecisionStageLogger(properties),
                        new ContextToolRegistry()),
                new StudentBrain(new LegacyMlBrain()));

        ResolvedDecisionBrain resolved = resolver.resolve();

        assertEquals(DecisionRuntimeMode.LLM_SHADOW, resolved.runtimeMode());
        assertTrue(resolved.shouldEvaluateWithLlm(DecisionStageName.PAIR_BUNDLE));
        assertTrue(resolved.shouldEvaluateWithLlm(DecisionStageName.DRIVER));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.PAIR_BUNDLE));
        assertFalse(resolved.shouldApplyAuthoritatively(DecisionStageName.FINAL_SELECTION));
    }
}
