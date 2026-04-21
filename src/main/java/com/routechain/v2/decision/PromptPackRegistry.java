package com.routechain.v2.decision;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class PromptPackRegistry {
    private final ObjectMapper objectMapper;

    public PromptPackRegistry(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String renderSystemPrompt(DecisionStageInputV1 input) {
        List<String> lines = new ArrayList<>();
        lines.add("Return strict JSON only.");
        lines.add("Do not invent ids outside the candidate window.");
        lines.add("Use the provided world state, reference frame, comparison pack, geospatial context, burst context, and upstream summaries only.");
        lines.add("Global pack: brain_guardrails, decision_policy, output_contract, reason_code_ontology.");
        lines.add("Stage pack: " + stagePackName(input.stageName()) + ".");
        if (!input.contextSelection().isEmpty()) {
            lines.add("State overlays: " + serialize(input.contextSelection().getOrDefault("overlays", List.of())) + ".");
            lines.add("Context profile: " + String.valueOf(input.contextSelection().getOrDefault("profileName", "balanced")) + ".");
            lines.add("Pass type: " + String.valueOf(input.contextSelection().getOrDefault("passType", "commit")) + ".");
            lines.add("Pass objective: " + String.valueOf(input.contextSelection().getOrDefault("passObjective", "finalize ranked decision")) + ".");
        }
        lines.add("Static prefix: " + String.valueOf(input.constraints().getOrDefault("staticPrefix", "")));
        lines.add("Evaluate candidates against eight packet layers: dispatch_context, candidate_window, reference_frame, comparison_pack, geospatial_context, burst_context, upstream_summary, and output_contract.");
        lines.add("Output contract: selectedIds plus rich assessments with id, score, rank, selected, confidence, reasonCodes, dominanceReasonCodes, regretToBestAlternative, driverFitSummary, routeVectorRefs, geospatialFlags, burstSensitivityFlags, rationale.");
        return String.join("\n", lines);
    }

    public String renderDynamicPrompt(DecisionStageInputV1 input) {
        LinkedHashMap<String, Object> stagePacket = new LinkedHashMap<>();
        stagePacket.put("dispatchContext", input.dispatchContext());
        stagePacket.put("candidateWindow", input.candidateSet());
        stagePacket.put("referenceFrame", input.referenceFrame());
        stagePacket.put("comparisonPack", input.comparisonPack());
        stagePacket.put("geospatialContext", input.geospatialContext());
        stagePacket.put("burstContext", input.burstContext());
        stagePacket.put("upstreamSummary", input.upstreamSummary());
        stagePacket.put("candidateSet", input.candidateSet());
        stagePacket.put("constraints", input.constraints());
        stagePacket.put("contextSelection", input.contextSelection());
        stagePacket.put("objectiveWeights", input.objectiveWeights());
        stagePacket.put("upstreamRefs", input.upstreamRefs());
        return serialize(stagePacket);
    }

    public Map<String, Object> outputContractMetadata() {
        return Map.of(
                "globalPack", List.of("brain_guardrails", "decision_policy", "output_contract", "reason_code_ontology"),
                "requiredAssessmentFields", List.of(
                        "id",
                        "score",
                        "rank",
                        "selected",
                        "confidence",
                        "reasonCodes",
                        "dominanceReasonCodes",
                        "regretToBestAlternative",
                        "driverFitSummary",
                        "routeVectorRefs",
                        "geospatialFlags",
                        "burstSensitivityFlags",
                        "rationale"));
    }

    private String stagePackName(DecisionStageName stageName) {
        return switch (stageName) {
            case PAIR_BUNDLE -> "pair_bundle_agent";
            case ANCHOR -> "anchor_agent";
            case DRIVER -> "driver_agent";
            case ROUTE_GENERATION -> "route_generation_agent";
            case ROUTE_CRITIQUE -> "route_critique_agent";
            case SCENARIO -> "scenario_agent";
            case FINAL_SELECTION -> "final_selection_agent";
            case OBSERVATION_PACK -> "observation_pack_agent";
            case SAFETY_EXECUTE -> "safety_execute_agent";
        };
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Failed to serialize prompt pack payload", exception);
        }
    }
}
