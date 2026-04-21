package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

public final class ContextToolRegistry {
    private static final List<String> DEFAULT_TOOLS = List.of(
            "get_bundle_details",
            "get_driver_details",
            "get_route_vector_summary",
            "get_conflict_summary",
            "get_scenario_breakdown");

    public Map<String, Object> toolManifest(DecisionStageName stageName) {
        return Map.of(
                "stageName", stageName == null ? "" : stageName.wireName(),
                "tools", DEFAULT_TOOLS.stream()
                        .map(toolName -> Map.of(
                                "name", toolName,
                                "enabled", stageName != null && stageName.supportsLlmDecision(),
                                "description", toolDescription(toolName)))
                        .toList(),
                "parallelToolCalls", false);
    }

    public Map<String, Object> toolResponse(String toolName, DecisionStageInputV1 input) {
        if (toolName == null || input == null) {
            return Map.of();
        }
            return switch (toolName) {
            case "get_bundle_details" -> Map.of(
                    "bundleWindow", input.candidateSet().getOrDefault("window", List.of()),
                    "referenceFrame", input.referenceFrame(),
                    "geospatialContext", input.geospatialContext());
            case "get_driver_details" -> Map.of(
                    "driverWindow", input.candidateSet().getOrDefault("window", List.of()),
                    "comparisonPack", input.comparisonPack(),
                    "geospatialContext", input.geospatialContext());
            case "get_route_vector_summary" -> Map.of(
                    "routeVectorWindow", input.candidateSet().getOrDefault("window", List.of()),
                    "comparisonPack", input.comparisonPack(),
                    "referenceFrame", input.referenceFrame());
            case "get_conflict_summary" -> Map.of(
                    "selectedIds", input.candidateSet().getOrDefault("selectedProposalIds", List.of()),
                    "comparisonPack", input.comparisonPack());
            case "get_scenario_breakdown" -> Map.of(
                    "scenarioWindow", input.candidateSet().getOrDefault("window", List.of()),
                    "burstContext", input.burstContext(),
                    "comparisonPack", input.comparisonPack());
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
