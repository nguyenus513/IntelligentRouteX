package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DecisionSessionStoreSafetyTest {

    @TempDir
    Path tempDir;

    @Test
    void sameTraceCanReadUpstreamStageRefs() {
        FileDecisionSessionStore store = fileStore();
        DecisionStageInputV1 pairBundleInput = stageInput("run-1", "tick-1", "trace-a", DecisionStageName.PAIR_BUNDLE, List.of("observation-pack"));
        store.beginSession(pairBundleInput);
        store.recordStageResult(pairBundleInput, stageOutput("trace-a", DecisionStageName.PAIR_BUNDLE), List.of(Map.of("passType", "commit")));

        DecisionSessionStore.SessionContext sessionContext = store.resolveContext(
                stageInput("run-1", "tick-1", "trace-a", DecisionStageName.ROUTE_CRITIQUE, List.of("pair-bundle")));

        assertEquals("run-1/tick-1/trace-a", sessionContext.sessionNamespace());
        assertEquals(5, sessionContext.sessionRefCount());
        assertTrue(sessionContext.sessionReadRefs().contains("stage:pair-bundle"));
        assertFalse(((List<?>) sessionContext.sessionRefs().get("priorStageResultRefs")).isEmpty());
    }

    @Test
    void differentTraceCannotReadSessionData() {
        FileDecisionSessionStore store = fileStore();
        DecisionStageInputV1 pairBundleInput = stageInput("run-1", "tick-1", "trace-a", DecisionStageName.PAIR_BUNDLE, List.of("observation-pack"));
        store.beginSession(pairBundleInput);
        store.recordStageResult(pairBundleInput, stageOutput("trace-a", DecisionStageName.PAIR_BUNDLE), List.of(Map.of("passType", "commit")));

        DecisionSessionStore.SessionContext sessionContext = store.resolveContext(
                stageInput("run-1", "tick-1", "trace-b", DecisionStageName.ROUTE_CRITIQUE, List.of("pair-bundle")));

        assertEquals(0, sessionContext.sessionRefCount());
        assertTrue(sessionContext.sessionReadRefs().isEmpty());
    }

    @Test
    void differentTickCannotReadSessionData() {
        FileDecisionSessionStore store = fileStore();
        DecisionStageInputV1 pairBundleInput = stageInput("run-1", "tick-1", "trace-a", DecisionStageName.PAIR_BUNDLE, List.of("observation-pack"));
        store.beginSession(pairBundleInput);
        store.recordStageResult(pairBundleInput, stageOutput("trace-a", DecisionStageName.PAIR_BUNDLE), List.of(Map.of("passType", "commit")));

        DecisionSessionStore.SessionContext sessionContext = store.resolveContext(
                stageInput("run-1", "tick-2", "trace-a", DecisionStageName.ROUTE_CRITIQUE, List.of("pair-bundle")));

        assertEquals(0, sessionContext.sessionRefCount());
        assertTrue(sessionContext.sessionReadRefs().isEmpty());
    }

    @Test
    void differentRunCannotReadSessionData() {
        FileDecisionSessionStore store = fileStore();
        DecisionStageInputV1 pairBundleInput = stageInput("run-1", "tick-1", "trace-a", DecisionStageName.PAIR_BUNDLE, List.of("observation-pack"));
        store.beginSession(pairBundleInput);
        store.recordStageResult(pairBundleInput, stageOutput("trace-a", DecisionStageName.PAIR_BUNDLE), List.of(Map.of("passType", "commit")));

        DecisionSessionStore.SessionContext sessionContext = store.resolveContext(
                stageInput("run-2", "tick-1", "trace-a", DecisionStageName.ROUTE_CRITIQUE, List.of("pair-bundle")));

        assertEquals(0, sessionContext.sessionRefCount());
        assertTrue(sessionContext.sessionReadRefs().isEmpty());
    }

    @Test
    void expiredSessionsAreCleanedUpBeforeNewSessionStarts() throws Exception {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().getLlm().getSessionStore().setBaseDir(tempDir.toString());
        properties.getDecision().getLlm().getSessionStore().setTtl(Duration.ofMillis(1));
        FileDecisionSessionStore store = new FileDecisionSessionStore(properties);
        DecisionStageInputV1 expiredInput = stageInput("run-expired", "tick-1", "trace-old", DecisionStageName.PAIR_BUNDLE, List.of("observation-pack"));
        store.beginSession(expiredInput);
        store.recordStageResult(expiredInput, stageOutput("trace-old", DecisionStageName.PAIR_BUNDLE), List.of(Map.of("passType", "commit")));
        Path expiredRoot = tempDir.resolve("run-expired").resolve("tick-1").resolve("trace-old");
        Files.setLastModifiedTime(expiredRoot, java.nio.file.attribute.FileTime.from(Instant.now().minusSeconds(120)));

        store.beginSession(stageInput("run-fresh", "tick-2", "trace-new", DecisionStageName.PAIR_BUNDLE, List.of("observation-pack")));

        assertFalse(Files.exists(expiredRoot));
        assertTrue(Files.exists(tempDir.resolve("run-fresh").resolve("tick-2").resolve("trace-new")));
    }

    @Test
    void v2PathUsesNoOpStoreAndExposesNoSessionState() {
        DecisionSessionStore store = new NoOpDecisionSessionStore();
        DecisionSessionStore.SessionContext sessionContext = store.resolveContext(
                stageInput("run-1", "tick-1", "trace-a", DecisionStageName.ROUTE_CRITIQUE, List.of("pair-bundle")));
        assertEquals(0, sessionContext.sessionRefCount());
        assertTrue(sessionContext.sessionReadRefs().isEmpty());
    }

    private FileDecisionSessionStore fileStore() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().getLlm().getSessionStore().setBaseDir(tempDir.toString());
        properties.getDecision().getLlm().getSessionStore().setTtl(Duration.ofMinutes(10));
        return new FileDecisionSessionStore(properties);
    }

    private DecisionStageInputV1 stageInput(String runId,
                                            String tickId,
                                            String traceId,
                                            DecisionStageName stageName,
                                            List<String> upstreamRefs) {
        return new DecisionStageInputV1(
                "stage-input-v1",
                traceId,
                runId,
                tickId,
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

    private DecisionStageOutputV1 stageOutput(String traceId, DecisionStageName stageName) {
        return new DecisionStageOutputV1(
                "stage-output-v1",
                traceId,
                "run-1",
                "tick-1",
                stageName,
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
    }
}
