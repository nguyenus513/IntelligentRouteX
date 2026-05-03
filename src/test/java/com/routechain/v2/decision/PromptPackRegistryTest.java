package com.routechain.v2.decision;

import com.fasterxml.jackson.databind.json.JsonMapper;
import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PromptPackRegistryTest {

    @Test
    void rendersStageSpecificSystemPromptAndPacket() {
        PromptPackRegistry registry = new PromptPackRegistry(JsonMapper.builder().findAndAddModules().build());
        PromptPackRegistry.RenderedPrompt rendered = registry.renderPrompt(stageInput(DecisionStageName.PAIR_BUNDLE));

        assertTrue(rendered.systemPrompt().contains("You are the pair-bundle decision module"));
        assertTrue(rendered.systemPrompt().contains("PAIR_SUPPORT_LENS"));
        assertTrue(rendered.dynamicPrompt().contains("\"schemaVersion\""));
        assertTrue(rendered.dynamicPrompt().contains("decision-stage-packet/v2"));
        assertTrue(rendered.dynamicPrompt().contains("bundleCandidates"));
        assertFalse(rendered.dynamicPrompt().contains("\"burstContext\""));
        assertEquals("decision-stage-prompt-spec/v1", rendered.metadata().get("promptSpecVersion"));
        assertEquals("pair-bundle", rendered.metadata().get("stagePromptName"));
        assertEquals("pair-bundle-visibility-v1", rendered.metadata().get("visibilityProfile"));
    }

    @Test
    void enforcesStageBudgetInRenderedPacket() {
        PromptPackRegistry registry = new PromptPackRegistry(JsonMapper.builder().findAndAddModules().build());
        PromptPackRegistry.RenderedPrompt rendered = registry.renderPrompt(stageInput(DecisionStageName.PAIR_BUNDLE));

        assertEquals(12, ((Number) ((Map<?, ?>) rendered.metadata().get("budgetApplied")).get("candidateLimit")).intValue());
        assertEquals(12, ((Number) rendered.metadata().get("candidateCountSeen")).intValue());
    }

    @Test
    void rendersV3PromptWithSkillsAndSessionRefs() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getDecision().getLlm().setPromptFamily("v3");
        PromptPackRegistry registry = new PromptPackRegistry(
                JsonMapper.builder().findAndAddModules().build(),
                properties.getDecision().getLlm(),
                new FixedDecisionSessionStore());

        PromptPackRegistry.RenderedPrompt rendered = registry.renderPrompt(stageInput(DecisionStageName.ROUTE_CRITIQUE));

        assertTrue(rendered.systemPrompt().contains("SKILL SET VERSION"));
        assertTrue(rendered.systemPrompt().contains("vector_compare"));
        assertTrue(rendered.dynamicPrompt().contains("decision-stage-packet/v3"));
        assertTrue(rendered.dynamicPrompt().contains("\"sessionRefs\""));
        assertEquals("decision-stage-prompt-spec/v3", rendered.metadata().get("promptSpecVersion"));
        assertEquals("decision-stage-skill-set/v1", rendered.metadata().get("skillSetVersion"));
        assertEquals(4, ((Number) rendered.metadata().get("sessionRefCount")).intValue());
        assertEquals(Boolean.TRUE, rendered.metadata().get("sessionStoreEnabled"));
        assertEquals("run-1/2026-04-20T00_00_00Z/trace-1", rendered.metadata().get("sessionNamespace"));
    }

    private DecisionStageInputV1 stageInput(DecisionStageName stageName) {
        List<Map<String, Object>> rows = java.util.stream.IntStream.range(0, 20)
                .mapToObj(index -> Map.<String, Object>of(
                        "id", "bundle-" + index,
                        "bundleId", "bundle-" + index,
                        "score", 0.5 + (index * 0.01),
                        "pickupLat", 10.0 + index,
                        "pickupLng", 106.0 + index,
                        "dropLat", 10.1 + index,
                        "dropLng", 106.1 + index,
                        "bundleCentroidLat", 10.05 + index,
                        "bundleCentroidLng", 106.05 + index))
                .toList();
        return new DecisionStageInputV1(
                "stage-input-v1",
                "trace-1",
                "run-1",
                Instant.parse("2026-04-20T00:00:00Z").toString(),
                stageName,
                Map.of(
                        "decisionMode", "legacy",
                        "authorityMode", "legacy",
                        "authoritativeStages", List.of("pair-bundle"),
                        "weatherClass", "clear",
                        "trafficClass", "normal",
                        "openOrderCount", 12,
                        "availableDriverCount", 6,
                        "decisionTime", Instant.parse("2026-04-20T00:00:00Z")),
                Map.of(
                        "topIds", rows.stream().map(row -> String.valueOf(row.get("id"))).limit(12).toList(),
                        "window", rows,
                        "bundleCount", 20,
                        "microClusterCount", 3,
                        "pairEdgeCount", 9),
                Map.of(
                        "stageName", stageName.wireName(),
                        "windowSize", 20,
                        "heuristicBaseline", Map.of("id", "bundle-0", "score", 0.8)),
                Map.of(
                        "windowSize", 20,
                        "items", List.of(Map.of("id", "bundle-0", "deltaToBaseline", 0.0))),
                Map.of(
                        "stageName", stageName.wireName(),
                        "corridorSummary", Map.of("corridorId", "corridor-1"),
                        "tileContextSummaries", List.of(Map.of("tileId", "tile-1")),
                        "selectedTiles", List.of(Map.of("tileId", "tile-1"))),
                Map.of("zoneBurstProbability", 0.2),
                Map.of("schemaContract", "stage_output_v1", "strictStructuredOutputs", true, "parallelToolCalls", false),
                Map.of("profileName", "compact", "compressed", true, "overlays", List.of(), "toolFetchPlan", List.of(), "qualityFlags", List.of(), "summary", "test", "selectedContext", Map.of()),
                Map.of("previousStage", "observation-pack"),
                Map.of("correctness", 0.35),
                List.of("observation-pack"));
    }

    private static final class FixedDecisionSessionStore extends NoOpDecisionSessionStore {
        @Override
        public boolean sessionStoreEnabled() {
            return true;
        }

        @Override
        public SessionContext resolveContext(DecisionStageInputV1 input) {
            return new SessionContext(Map.of(
                    "priorStageResultRefs", List.of(Map.of("stageName", "route-generation")),
                    "routeVectorRefs", List.of("proposal-1"),
                    "tileContextRefs", List.of("tile-1"),
                    "selectedCandidateRefs", List.of("proposal-1"),
                    "critiqueRefs", List.of("route-dominated")),
                    4,
                    "run-1/2026-04-20T00_00_00Z/trace-1",
                    List.of("stage:route-generation", "route-vector:proposal-1", "tile-context:tile-1", "critique:route-dominated"));
        }
    }
}
