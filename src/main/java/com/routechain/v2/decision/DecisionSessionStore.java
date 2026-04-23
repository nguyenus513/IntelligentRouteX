package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

public interface DecisionSessionStore extends AutoCloseable {

    SessionStartResult beginSession(DecisionStageInputV1 input);

    SessionContext resolveContext(DecisionStageInputV1 input);

    void recordPass(DecisionStageInputV1 input,
                    String passType,
                    PromptPackRegistry.RenderedPrompt renderedPrompt,
                    NineRouterResponsesClient.LlmInvocationResult result);

    StageSessionRecord recordStageResult(DecisionStageInputV1 input,
                                         DecisionStageOutputV1 output,
                                         List<Map<String, Object>> passSummaries);

    @Override
    default void close() {
    }

    record SessionStartResult(
            boolean created,
            Map<String, Object> manifest) {
    }

    record SessionContext(
            Map<String, Object> sessionRefs,
            int sessionRefCount) {

        static SessionContext empty() {
            return new SessionContext(Map.of(
                    "priorStageResultRefs", List.of(),
                    "routeVectorRefs", List.of(),
                    "tileContextRefs", List.of(),
                    "selectedCandidateRefs", List.of(),
                    "critiqueRefs", List.of()), 0);
        }
    }

    record StageSessionRecord(
            Map<String, Object> stageSummary,
            Map<String, Object> stageRefs) {
    }
}
