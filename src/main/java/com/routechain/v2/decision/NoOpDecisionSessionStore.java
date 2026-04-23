package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

public class NoOpDecisionSessionStore implements DecisionSessionStore {
    @Override
    public SessionStartResult beginSession(DecisionStageInputV1 input) {
        return new SessionStartResult(false, Map.of());
    }

    @Override
    public SessionContext resolveContext(DecisionStageInputV1 input) {
        return SessionContext.empty();
    }

    @Override
    public void recordPass(DecisionStageInputV1 input,
                           String passType,
                           PromptPackRegistry.RenderedPrompt renderedPrompt,
                           NineRouterResponsesClient.LlmInvocationResult result) {
    }

    @Override
    public StageSessionRecord recordStageResult(DecisionStageInputV1 input,
                                                DecisionStageOutputV1 output,
                                                List<Map<String, Object>> passSummaries) {
        return new StageSessionRecord(Map.of(), Map.of());
    }
}
