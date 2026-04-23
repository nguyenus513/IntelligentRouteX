package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FileDecisionSessionStoreTest {

    @TempDir
    Path tempDir;

    @Test
    void resolvesStageRefsOnlyWithinSameTrace() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().getLlm().getSessionStore().setBaseDir(tempDir.toString());
        FileDecisionSessionStore store = new FileDecisionSessionStore(properties);

        DecisionStageInputV1 pairBundleInput = stageInput("trace-a", DecisionStageName.PAIR_BUNDLE, List.of("observation-pack"));
        store.beginSession(pairBundleInput);
        DecisionStageOutputV1 output = new DecisionStageOutputV1(
                "stage-output-v1",
                "trace-a",
                "run-1",
                "tick-1",
                DecisionStageName.PAIR_BUNDLE,
                DecisionBrainType.LLM,
                "cx/gpt-5.4",
                Map.of(
                        "summary", "ok",
                        "reasonCodes", List.of("pair-support-strong"),
                        "items", List.of(Map.of(
                                "id", "proposal-1",
                                "routeVectorRefs", List.of("proposal-1"),
                                "dominanceReasonCodes", List.of("route-dominated")))),
                List.of("proposal-1"),
                new DecisionStageMetaV1(
                        "decision-stage-meta/v1",
                        1L,
                        0.8,
                        false,
                        "",
                        true,
                        "llm",
                        "medium",
                        "medium",
                        Map.of(),
                        0,
                        "hash",
                        "llm",
                        List.of(),
                        List.of(),
                        "balanced",
                        List.of(),
                        false,
                        "test"));
        store.recordStageResult(pairBundleInput, output, List.of(Map.of("passType", "commit")));

        DecisionStageInputV1 sameTraceRoute = stageInput("trace-a", DecisionStageName.ROUTE_CRITIQUE, List.of("pair-bundle"));
        DecisionSessionStore.SessionContext sameTraceContext = store.resolveContext(sameTraceRoute);
        assertEquals(5, sameTraceContext.sessionRefCount());
        assertFalse(((List<?>) sameTraceContext.sessionRefs().get("priorStageResultRefs")).isEmpty());

        DecisionStageInputV1 otherTraceRoute = stageInput("trace-b", DecisionStageName.ROUTE_CRITIQUE, List.of("pair-bundle"));
        DecisionSessionStore.SessionContext otherTraceContext = store.resolveContext(otherTraceRoute);
        assertTrue(((List<?>) otherTraceContext.sessionRefs().get("priorStageResultRefs")).isEmpty());
        assertEquals(0, otherTraceContext.sessionRefCount());
    }

    private DecisionStageInputV1 stageInput(String traceId, DecisionStageName stageName, List<String> upstreamRefs) {
        return new DecisionStageInputV1(
                "stage-input-v1",
                traceId,
                "run-1",
                Instant.parse("2026-04-20T00:00:00Z").toString(),
                stageName,
                Map.of("decisionMode", "llm", "authorityMode", "llm-shadow"),
                Map.of("topIds", List.of("proposal-1"), "window", List.of(Map.of("id", "proposal-1"))),
                Map.of(),
                Map.of(),
                Map.of("selectedTiles", List.of(Map.of("tileId", "tile-1"))),
                Map.of(),
                Map.of(),
                Map.of(),
                Map.of(),
                Map.of(),
                upstreamRefs);
    }
}
