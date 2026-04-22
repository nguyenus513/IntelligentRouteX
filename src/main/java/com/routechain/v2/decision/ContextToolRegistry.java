package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

public final class ContextToolRegistry {
    private final StageVisibilityPolicy visibilityPolicy = new StageVisibilityPolicy();

    private static final List<String> DEFAULT_TOOLS = List.of(
            "get_bundle_details",
            "get_driver_details",
            "get_route_vector_summary",
            "get_conflict_summary",
            "get_scenario_breakdown");

    public Map<String, Object> toolManifest(DecisionStageName stageName) {
        List<String> allowedTools = visibilityPolicy.allowedTools(stageName);
        return Map.of(
                "stageName", stageName == null ? "" : stageName.wireName(),
                "tools", DEFAULT_TOOLS.stream()
                        .map(toolName -> Map.of(
                                "name", toolName,
                                "enabled", stageName != null && stageName.supportsLlmDecision() && allowedTools.contains(toolName),
                                "description", toolDescription(toolName)))
                        .toList(),
                "parallelToolCalls", false);
    }

    public Map<String, Object> toolResponse(String toolName, DecisionStageInputV1 input) {
        if (toolName == null || input == null) {
            return Map.of();
        }
        if (!visibilityPolicy.allowedTools(input.stageName()).contains(toolName)) {
            return Map.of(
                    "toolName", toolName,
                    "status", "not-allowed-for-stage",
                    "stageName", input.stageName().wireName());
        }
        return switch (toolName) {
            case "get_bundle_details" -> Map.of(
                    "bundleWindow", input.candidateSet().getOrDefault("window", List.of()),
                    "referenceFrame", visibilityPolicy.referenceFrame(input),
                    "geospatialContext", visibilityPolicy.geospatialContext(input));
            case "get_driver_details" -> Map.of(
                    "driverWindow", input.candidateSet().getOrDefault("window", List.of()),
                    "comparisonPack", visibilityPolicy.comparisonPack(input),
                    "geospatialContext", visibilityPolicy.geospatialContext(input));
            case "get_route_vector_summary" -> Map.of(
                    "routeVectorWindow", input.candidateSet().getOrDefault("window", List.of()),
                    "comparisonPack", visibilityPolicy.comparisonPack(input),
                    "referenceFrame", visibilityPolicy.referenceFrame(input));
            case "get_conflict_summary" -> Map.of(
                    "selectedIds", input.candidateSet().getOrDefault("selectedProposalIds", List.of()),
                    "comparisonPack", visibilityPolicy.comparisonPack(input),
                    "upstreamSummary", visibilityPolicy.upstreamSummary(input));
            case "get_scenario_breakdown" -> Map.of(
                    "scenarioWindow", input.candidateSet().getOrDefault("window", List.of()),
                    "burstContext", input.burstContext(),
                    "comparisonPack", visibilityPolicy.comparisonPack(input));
            default -> Map.of();
        };
    }

    private String toolDescription(String toolName) {
        return switch (toolName) {
            case "get_bundle_details" -> "Fetch bounded bundle candidate details.";
            case "get_driver_details" -> "Fetch bounded driver shortlist details.";
            case "get_route_vector_summary" -> "Fetch route-vector summary rows.";
            case "get_conflict_summary" -> "Fetch selector conflict summary rows.";
            case "get_scenario_breakdown" -> "Fetch scenario utility rows.";
            default -> "Unknown tool";
        };
    }
}
