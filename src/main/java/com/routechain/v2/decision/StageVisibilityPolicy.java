package com.routechain.v2.decision;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

final class StageVisibilityPolicy {

    Map<String, Object> candidateWindow(DecisionStageInputV1 input, List<Map<String, Object>> limitedRows) {
        Map<String, Object> candidateSet = input.candidateSet();
        return switch (input.stageName()) {
            case OBSERVATION_PACK -> Map.of(
                    "kind", "observation-window",
                    "packetSafetyOnly", true,
                    "topIds", List.of(),
                    "window", List.of(),
                    "sourceAvailability", sourceAvailability(input.dispatchContext()));
            case PAIR_BUNDLE -> candidateWindowMap("pair-bundle-window", "bundleCandidates", limitedRows, candidateSet, List.of("bundleCount", "microClusterCount", "pairEdgeCount"));
            case ANCHOR -> candidateWindowMap("anchor-window", "anchorCandidates", limitedRows, candidateSet, List.of("anchorCount"));
            case DRIVER -> candidateWindowMap("driver-window", "driverCandidates", limitedRows, candidateSet, List.of("driverCandidateCount"));
            case ROUTE_GENERATION -> candidateWindowMap("route-generation-window", "routeProposals", limitedRows, candidateSet, List.of("proposalCount"));
            case ROUTE_CRITIQUE -> candidateWindowMap("route-critique-window", "routeProposals", limitedRows, candidateSet, List.of("proposalCount", "geometryAvailableCount"));
            case SCENARIO -> candidateWindowMap("scenario-window", "scenarioCandidates", limitedRows, candidateSet, List.of("robustUtilityCount", "scenarioEvaluationCount"));
            case FINAL_SELECTION -> candidateWindowMap("final-selection-window", "finalProposals", limitedRows, candidateSet, List.of("selectorCandidateCount", "selectedProposalIds"));
            case SAFETY_EXECUTE -> Map.of(
                    "kind", "safety-execute-window",
                    "assignmentIds", listValue(candidateSet.get("topIds")),
                    "assignmentCount", candidateSet.getOrDefault("assignmentCount", 0));
        };
    }

    Map<String, Object> dispatchContext(DecisionStageInputV1 input) {
        return pick(input.dispatchContext(),
                "decisionTime",
                "hourBucket",
                "dayType",
                "weatherProfile",
                "weatherClass",
                "trafficClass",
                "baselineEtaMinutes",
                "liveEtaMinutes",
                "uncertainty",
                "trafficBad",
                "weatherBad",
                "corridorSignature",
                "zoneId",
                "decisionMode",
                "authorityMode",
                "authoritativeStages",
                "systemLoad",
                "openOrderCount",
                "availableDriverCount",
                "supplyDemandRatio",
                "lateHour");
    }

    Map<String, Object> referenceFrame(DecisionStageInputV1 input) {
        return switch (input.stageName()) {
            case OBSERVATION_PACK, SAFETY_EXECUTE -> Map.of();
            case PAIR_BUNDLE, ANCHOR, DRIVER, ROUTE_GENERATION, ROUTE_CRITIQUE, SCENARIO, FINAL_SELECTION -> pick(input.referenceFrame(),
                    "stageName",
                    "windowSize",
                    "fastestEta",
                    "lowestCost",
                    "safest",
                    "closestDriverEntry",
                    "heuristicBaseline",
                    "medianSummary");
        };
    }

    Map<String, Object> comparisonPack(DecisionStageInputV1 input) {
        return switch (input.stageName()) {
            case OBSERVATION_PACK, SAFETY_EXECUTE -> Map.of();
            case PAIR_BUNDLE, ANCHOR, DRIVER, ROUTE_GENERATION -> pick(input.comparisonPack(), "windowSize", "items");
            case ROUTE_CRITIQUE, SCENARIO, FINAL_SELECTION -> pick(input.comparisonPack(), "windowSize", "items", "llmPassFeedback");
        };
    }

    Map<String, Object> geospatialContext(DecisionStageInputV1 input) {
        return switch (input.stageName()) {
            case OBSERVATION_PACK -> pick(input.geospatialContext(), "stageName", "zoneId", "corridorId", "selectedTiles", "tileContextSummaries");
            case PAIR_BUNDLE -> pick(input.geospatialContext(), "stageName", "pickupDropClusterSummary", "corridorSummary", "selectedTiles", "tileContextSummaries");
            case ANCHOR -> pick(input.geospatialContext(), "stageName", "pickupDropClusterSummary", "corridorSummary", "tileContextSummaries");
            case DRIVER -> pick(input.geospatialContext(), "stageName", "localDriverAreaSummary", "corridorSummary", "geospatialReferenceFrame");
            case ROUTE_GENERATION -> pick(input.geospatialContext(), "stageName", "corridorSummary", "tileContextSummaries", "geospatialReferenceFrame");
            case ROUTE_CRITIQUE -> pick(input.geospatialContext(), "stageName", "corridorSummary", "tileContextSummaries", "geospatialReferenceFrame", "selectedTiles");
            case SCENARIO -> pick(input.geospatialContext(), "stageName", "corridorSummary", "geospatialReferenceFrame");
            case FINAL_SELECTION -> pick(input.geospatialContext(), "stageName", "corridorSummary", "geospatialReferenceFrame");
            case SAFETY_EXECUTE -> Map.of();
        };
    }

    Map<String, Object> upstreamSummary(DecisionStageInputV1 input) {
        return switch (input.stageName()) {
            case OBSERVATION_PACK -> Map.of();
            case PAIR_BUNDLE, ANCHOR, DRIVER, ROUTE_GENERATION, ROUTE_CRITIQUE, SCENARIO, FINAL_SELECTION, SAFETY_EXECUTE -> input.upstreamSummary();
        };
    }

    Map<String, Object> constraints(DecisionStageInputV1 input) {
        return pick(input.constraints(), "schemaContract", "strictStructuredOutputs", "parallelToolCalls", "toolManifest");
    }

    Map<String, Double> objectiveWeights(DecisionStageInputV1 input) {
        return switch (input.stageName()) {
            case OBSERVATION_PACK, SAFETY_EXECUTE -> Map.of();
            case PAIR_BUNDLE, ANCHOR, DRIVER, ROUTE_GENERATION, ROUTE_CRITIQUE, SCENARIO, FINAL_SELECTION -> input.objectiveWeights();
        };
    }

    String visibilityProfile(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> "observation-visibility-v1";
            case PAIR_BUNDLE -> "pair-bundle-visibility-v1";
            case ANCHOR -> "anchor-visibility-v1";
            case DRIVER -> "driver-visibility-v1";
            case ROUTE_GENERATION -> "route-generation-visibility-v1";
            case ROUTE_CRITIQUE -> "route-critique-visibility-v1";
            case SCENARIO -> "scenario-visibility-v1";
            case FINAL_SELECTION -> "final-selection-visibility-v1";
            case SAFETY_EXECUTE -> "safety-execute-visibility-v1";
        };
    }

    List<String> allowedTools(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> List.of();
            case PAIR_BUNDLE, ANCHOR -> List.of("get_bundle_details");
            case DRIVER -> List.of("get_driver_details");
            case ROUTE_GENERATION -> List.of("get_driver_details", "get_route_vector_summary");
            case ROUTE_CRITIQUE -> List.of("get_route_vector_summary");
            case SCENARIO -> List.of("get_scenario_breakdown");
            case FINAL_SELECTION -> List.of("get_conflict_summary", "get_route_vector_summary", "get_scenario_breakdown");
            case SAFETY_EXECUTE -> List.of("get_conflict_summary");
        };
    }

    double comparisonPackCoverage(DecisionStageName stageName, Map<String, Object> comparisonPack) {
        List<String> expected = switch (stageName) {
            case OBSERVATION_PACK, SAFETY_EXECUTE -> List.of();
            case ROUTE_CRITIQUE, SCENARIO, FINAL_SELECTION -> List.of("windowSize", "items", "llmPassFeedback");
            default -> List.of("windowSize", "items");
        };
        return coverage(expected, comparisonPack);
    }

    double geospatialCoverage(DecisionStageName stageName, Map<String, Object> geospatialContext) {
        List<String> expected = switch (stageName) {
            case OBSERVATION_PACK -> List.of("selectedTiles", "tileContextSummaries");
            case PAIR_BUNDLE, ANCHOR -> List.of("corridorSummary", "tileContextSummaries");
            case DRIVER -> List.of("localDriverAreaSummary", "corridorSummary");
            case ROUTE_GENERATION, ROUTE_CRITIQUE -> List.of("corridorSummary", "geospatialReferenceFrame");
            case SCENARIO, FINAL_SELECTION -> List.of("corridorSummary");
            case SAFETY_EXECUTE -> List.of();
        };
        return coverage(expected, geospatialContext);
    }

    List<String> missingContextFlags(DecisionStageInputV1 input,
                                     Map<String, Object> comparisonPack,
                                     Map<String, Object> geospatialContext,
                                     Map<String, Object> candidateWindow) {
        LinkedHashSet<String> flags = new LinkedHashSet<>();
        if (candidateCount(candidateWindow) == 0 && input.stageName() != DecisionStageName.OBSERVATION_PACK) {
            flags.add("candidate-window-empty");
        }
        if (comparisonPackCoverage(input.stageName(), comparisonPack) < 1.0) {
            flags.add("comparison-pack-partial");
        }
        if (geospatialCoverage(input.stageName(), geospatialContext) < 1.0) {
            flags.add("geospatial-context-partial");
        }
        if (dispatchModeMissing(input.dispatchContext())) {
            flags.add("dispatch-context-incomplete");
        }
        return List.copyOf(flags);
    }

    int candidateCount(Map<String, Object> candidateWindow) {
        for (String key : List.of("bundleCandidates", "anchorCandidates", "driverCandidates", "routeProposals", "scenarioCandidates", "finalProposals", "window", "assignmentIds")) {
            Object value = candidateWindow.get(key);
            if (value instanceof List<?> list) {
                return list.size();
            }
        }
        return 0;
    }

    private Map<String, Object> candidateWindowMap(String kind,
                                                   String windowKey,
                                                   List<Map<String, Object>> limitedRows,
                                                   Map<String, Object> candidateSet,
                                                   List<String> passthroughKeys) {
        LinkedHashMap<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", kind);
        payload.put("topIds", listValue(candidateSet.get("topIds")));
        payload.put(windowKey, limitedRows);
        payload.put("windowCount", limitedRows.size());
        for (String key : passthroughKeys) {
            if (candidateSet.containsKey(key)) {
                payload.put(key, candidateSet.get(key));
            }
        }
        return Map.copyOf(payload);
    }

    private Map<String, Object> pick(Map<String, Object> source, String... keys) {
        if (source == null || source.isEmpty()) {
            return Map.of();
        }
        LinkedHashMap<String, Object> picked = new LinkedHashMap<>();
        for (String key : keys) {
            if (source.containsKey(key)) {
                Object value = source.get(key);
                if (value instanceof List<?> list) {
                    picked.put(key, new ArrayList<>(list));
                } else {
                    picked.put(key, value);
                }
            }
        }
        return Map.copyOf(picked);
    }

    private List<String> listValue(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return list.stream().map(String::valueOf).toList();
    }

    private Map<String, Object> sourceAvailability(Map<String, Object> dispatchContext) {
        return Map.of(
                "weatherClass", dispatchContext.getOrDefault("weatherClass", "unknown"),
                "trafficClass", dispatchContext.getOrDefault("trafficClass", "unknown"),
                "authorityMode", dispatchContext.getOrDefault("authorityMode", "unknown"),
                "decisionMode", dispatchContext.getOrDefault("decisionMode", "unknown"));
    }

    private double coverage(List<String> expected, Map<String, Object> source) {
        if (expected.isEmpty()) {
            return 1.0;
        }
        long present = expected.stream().filter(key -> source != null && source.containsKey(key) && !emptyValue(source.get(key))).count();
        return present / (double) expected.size();
    }

    private boolean dispatchModeMissing(Map<String, Object> dispatchContext) {
        return emptyValue(dispatchContext.get("decisionMode")) || emptyValue(dispatchContext.get("authorityMode"));
    }

    private boolean emptyValue(Object value) {
        if (value == null) {
            return true;
        }
        if (value instanceof String text) {
            return text.isBlank();
        }
        if (value instanceof List<?> list) {
            return list.isEmpty();
        }
        if (value instanceof Map<?, ?> map) {
            return map.isEmpty();
        }
        return false;
    }
}
