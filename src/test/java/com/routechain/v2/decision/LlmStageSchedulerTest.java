package com.routechain.v2.decision;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LlmStageSchedulerTest {

    @Test
    void capsRouteCritiqueToSingleLowEffortPass() {
        StubTransport transport = new StubTransport(List.of("proposal-1"));
        LlmStageScheduler scheduler = scheduler(transport);

        DecisionStageOutputV1 output = scheduler.evaluate(stageInput(DecisionStageName.ROUTE_CRITIQUE));

        assertEquals(1, transport.postBodies.size());
        assertEquals(1, ((Number) output.meta().tokenUsage().get("requestCount")).intValue());
        assertEquals("low", output.meta().requestedEffort());
        assertTrue(output.meta().decisionQualityFlags().contains("llm-pass-count-1"));
        assertTrue(output.meta().decisionQualityFlags().contains("llm-pass-plan-single-pass"));
        assertTrue(output.meta().decisionQualityFlags().contains("effort-override-route-critique-low"));
    }

    @Test
    void keepsFinalSelectionSinglePass() {
        StubTransport transport = new StubTransport(List.of("proposal-1", "proposal-2", "proposal-3"));
        LlmStageScheduler scheduler = scheduler(transport);

        DecisionStageOutputV1 output = scheduler.evaluate(stageInput(DecisionStageName.FINAL_SELECTION));

        assertEquals(1, transport.postBodies.size());
        assertEquals(3, output.selectedIds().size());
        assertEquals("low", output.meta().requestedEffort());
        assertTrue(output.meta().decisionQualityFlags().contains("llm-pass-count-1"));
        assertTrue(output.meta().decisionQualityFlags().contains("llm-pass-plan-single-pass"));
    }

    @Test
    void guardsSelectionShrinkWithoutHardRiskReason() {
        StubTransport transport = new StubTransport(List.of("proposal-1"));
        LlmStageScheduler scheduler = scheduler(transport);

        DecisionStageOutputV1 output = scheduler.evaluate(stageInput(DecisionStageName.FINAL_SELECTION));

        assertEquals(List.of("proposal-1", "proposal-2", "proposal-3"), output.selectedIds());
        assertEquals("llm-guarded", output.meta().appliedSource());
        assertEquals("llm-authority-selection-shrink-guard-triggered", output.meta().fallbackReason());
        assertTrue(output.meta().decisionQualityFlags().contains("llm-authority-selection-shrink-guard-triggered"));
    }

    @Test
    void allowsSelectionShrinkWithHardRiskReason() {
        StubTransport transport = new StubTransport(List.of("proposal-1"), List.of("conflict-risk"));
        LlmStageScheduler scheduler = scheduler(transport);

        DecisionStageOutputV1 output = scheduler.evaluate(stageInput(DecisionStageName.FINAL_SELECTION));

        assertEquals(List.of("proposal-1"), output.selectedIds());
        assertEquals("llm", output.meta().appliedSource());
    }

    private LlmStageScheduler scheduler(StubTransport transport) {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getFeedback().setDecisionLogEnabled(false);
        properties.getDecision().getLlm().setApiKeyEnv("PATH");
        NineRouterResponsesClient client = new NineRouterResponsesClient(
                properties.getDecision().getLlm(),
                transport,
                JsonMapper.builder().findAndAddModules().build());
        return new LlmStageScheduler(
                client,
                properties.getDecision(),
                new DecisionStageLogger(properties),
                new NoOpDecisionSessionStore());
    }

    private DecisionStageInputV1 stageInput(DecisionStageName stageName) {
        List<String> topIds = List.of("proposal-1", "proposal-2", "proposal-3", "proposal-4");
        return new DecisionStageInputV1(
                "stage-input-v1",
                "trace-1",
                "run-1",
                Instant.parse("2026-04-20T00:00:00Z").toString(),
                stageName,
                Map.of(
                        "decisionMode", "llm-authoritative",
                        "authorityMode", "llm",
                        "authoritativeStages", List.of("route-critique", "final-selection")),
                Map.of(
                        "topIds", topIds,
                        "proposalCount", topIds.size(),
                        "selectorCandidateCount", topIds.size(),
                        "window", topIds.stream().map(id -> Map.<String, Object>of("id", id, "score", 0.8)).toList()),
                Map.of("heuristicBaseline", Map.of("id", "proposal-1", "score", 0.8)),
                Map.of("items", List.of()),
                Map.of("stageName", stageName.wireName(), "corridorSummary", Map.of("trafficLevel", "normal")),
                Map.of(),
                Map.of(),
                Map.of("profileName", "compact-staging", "compressed", true, "overlays", List.of(), "toolFetchPlan", List.of(), "qualityFlags", List.of("context-forced-compact")),
                Map.of(),
                Map.of(),
                List.of());
    }

    private static final class StubTransport implements NineRouterResponsesClient.ResponsesTransport {
        private final List<String> selectedIds;
        private final List<String> reasonCodes;
        private final List<JsonNode> postBodies = new ArrayList<>();

        private StubTransport(List<String> selectedIds) {
            this(selectedIds, List.of());
        }

        private StubTransport(List<String> selectedIds, List<String> reasonCodes) {
            this.selectedIds = selectedIds;
            this.reasonCodes = reasonCodes;
        }

        @Override
        public NineRouterResponsesClient.TransportResponse get(String baseUrl,
                                                               String apiKey,
                                                               Duration timeout,
                                                               ObjectMapper objectMapper,
                                                               String relativePath) {
            return new NineRouterResponsesClient.TransportResponse(200, "{\"data\":[{\"id\":\"cx/gpt-5.5\"}]}");
        }

        @Override
        public NineRouterResponsesClient.TransportResponse post(String baseUrl,
                                                                String apiKey,
                                                                Duration timeout,
                                                                JsonNode requestBody,
                                                                ObjectMapper objectMapper) {
            postBodies.add(requestBody);
            try {
                String selected = objectMapper.writeValueAsString(selectedIds);
                String reasons = objectMapper.writeValueAsString(reasonCodes);
                String stageOutput = "{\"selectedIds\":" + selected + ",\"assessments\":{\"summary\":\"ok\",\"reasonCodes\":" + reasons + ",\"items\":[]}}";
                return new NineRouterResponsesClient.TransportResponse(
                        200,
                        "{\"output\":[{\"content\":[{\"text\":" + objectMapper.writeValueAsString(stageOutput) + "}]}],\"usage\":{\"input_tokens\":10,\"output_tokens\":5,\"total_tokens\":15}}");
            } catch (Exception exception) {
                throw new IllegalStateException(exception);
            }
        }
    }
}
