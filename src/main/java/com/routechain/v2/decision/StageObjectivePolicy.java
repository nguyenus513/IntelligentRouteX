package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

final class StageObjectivePolicy {

    String missionFor(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> "normalize and validate the decision packet and world-state context";
            case PAIR_BUNDLE -> "retain the strongest pair and bundle candidates worth advancing";
            case ANCHOR -> "choose stable pickup anchors for retained bundles";
            case DRIVER -> "rerank the strongest driver shortlist for each bundle and anchor";
            case ROUTE_GENERATION -> "generate feasible and diverse route proposals";
            case ROUTE_CRITIQUE -> "critique and rerank route proposals using route-vector realism";
            case SCENARIO -> "score proposal robustness under traffic, weather, and burst overlays";
            case FINAL_SELECTION -> "select the final global proposal set";
            case SAFETY_EXECUTE -> "validate and normalize the final execution envelope";
        };
    }

    List<String> mustDoFor(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> List.of("report missing sources", "report packet safety flags", "normalize visible context");
            case PAIR_BUNDLE -> List.of("rank retained pair or bundle candidates", "explain compactness and spread", "flag weak candidates");
            case ANCHOR -> List.of("rank anchors by stability", "flag risky anchors", "stay within provided anchor candidates");
            case DRIVER -> List.of("rank drivers by fit and corridor entry quality", "explain deadhead and fit tradeoffs", "produce a shortlist only");
            case ROUTE_GENERATION -> List.of("produce diverse feasible routes", "avoid duplicate route ideas", "stay within provided driver and bundle context");
            case ROUTE_CRITIQUE -> List.of("identify dominated routes", "estimate regret", "justify route ranking with route vectors");
            case SCENARIO -> List.of("score robustness under overlays", "flag burst sensitivity", "compare proposal resilience");
            case FINAL_SELECTION -> List.of("choose the best final proposal", "balance value and conflict safety", "return a confidence-backed ranking");
            case SAFETY_EXECUTE -> List.of("validate assignments", "report safety flags", "preserve selected ids");
        };
    }

    List<String> mustNotDoFor(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> List.of("do not rank candidates", "do not generate routes", "do not choose final selectedIds");
            case PAIR_BUNDLE -> List.of("do not choose drivers", "do not generate routes", "do not solve downstream stages");
            case ANCHOR -> List.of("do not choose drivers", "do not invent bundles", "do not solve downstream stages");
            case DRIVER -> List.of("do not finalize assignments", "do not invent drivers", "do not generate new bundles");
            case ROUTE_GENERATION -> List.of("do not critique deeply", "do not finalize selection", "do not invent ids outside the packet");
            case ROUTE_CRITIQUE -> List.of("do not invent routes", "do not change candidate universe", "do not solve final selection");
            case SCENARIO -> List.of("do not generate new proposals", "do not ignore overlays", "do not finalize execution");
            case FINAL_SELECTION -> List.of("do not invent proposals", "do not ignore conflict summaries", "do not rewrite execution assignments");
            case SAFETY_EXECUTE -> List.of("do not optimize again", "do not invent assignments", "do not replace selected proposals");
        };
    }

    List<String> allowedInputsFor(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> List.of("dispatchContext", "geospatialContext", "constraints");
            case PAIR_BUNDLE -> List.of("dispatchContext", "candidateWindow", "referenceFrame", "comparisonPack", "geospatialContext", "upstreamSummary");
            case ANCHOR -> List.of("dispatchContext", "candidateWindow", "referenceFrame", "comparisonPack", "geospatialContext", "upstreamSummary");
            case DRIVER -> List.of("dispatchContext", "candidateWindow", "referenceFrame", "comparisonPack", "geospatialContext", "upstreamSummary");
            case ROUTE_GENERATION -> List.of("dispatchContext", "candidateWindow", "referenceFrame", "comparisonPack", "geospatialContext", "upstreamSummary");
            case ROUTE_CRITIQUE -> List.of("dispatchContext", "candidateWindow", "referenceFrame", "comparisonPack", "geospatialContext", "upstreamSummary");
            case SCENARIO -> List.of("dispatchContext", "candidateWindow", "comparisonPack", "geospatialContext", "upstreamSummary");
            case FINAL_SELECTION -> List.of("dispatchContext", "candidateWindow", "comparisonPack", "upstreamSummary", "constraints");
            case SAFETY_EXECUTE -> List.of("dispatchContext", "candidateWindow", "constraints", "upstreamSummary");
        };
    }

    String objectiveFor(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> "maximize packet correctness and context safety";
            case PAIR_BUNDLE -> "maximize retained bundle quality under compactness and support";
            case ANCHOR -> "maximize anchor stability and route viability";
            case DRIVER -> "maximize driver fit with low deadhead and stable corridor entry";
            case ROUTE_GENERATION -> "maximize route feasibility and proposal diversity";
            case ROUTE_CRITIQUE -> "maximize realistic route quality and minimize dominance regret";
            case SCENARIO -> "maximize robustness to degraded conditions and burst shifts";
            case FINAL_SELECTION -> "maximize global value while staying conflict-free and robust";
            case SAFETY_EXECUTE -> "maximize execution safety and envelope validity";
        };
    }

    Map<String, Object> outputRequirementsFor(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> Map.of("selectedIdsPolicy", "empty-or-pass-through-only", "assessmentEmphasis", List.of("contextQualityFlags", "missingSourceFlags", "packetSafetyFlags"));
            case PAIR_BUNDLE -> Map.of("selectedIdsPolicy", "retained-pair-or-bundle-ids", "assessmentEmphasis", List.of("rank", "reasonCodes", "dominanceReasonCodes", "regretToBestAlternative"));
            case ANCHOR -> Map.of("selectedIdsPolicy", "anchor-ids-only", "assessmentEmphasis", List.of("rank", "confidence", "reasonCodes", "geospatialFlags"));
            case DRIVER -> Map.of("selectedIdsPolicy", "driver-shortlist-only", "assessmentEmphasis", List.of("rank", "driverFitSummary", "reasonCodes", "geospatialFlags"));
            case ROUTE_GENERATION -> Map.of("selectedIdsPolicy", "proposal-ids-only", "assessmentEmphasis", List.of("rank", "routeVectorRefs", "reasonCodes", "rationale"));
            case ROUTE_CRITIQUE -> Map.of("selectedIdsPolicy", "proposal-ids-only", "assessmentEmphasis", List.of("rank", "dominanceReasonCodes", "regretToBestAlternative", "routeVectorRefs"));
            case SCENARIO -> Map.of("selectedIdsPolicy", "proposal-ids-only", "assessmentEmphasis", List.of("rank", "burstSensitivityFlags", "reasonCodes", "confidence"));
            case FINAL_SELECTION -> Map.of("selectedIdsPolicy", "final-proposal-ids", "assessmentEmphasis", List.of("rank", "confidence", "reasonCodes", "dominanceReasonCodes"));
            case SAFETY_EXECUTE -> Map.of("selectedIdsPolicy", "selected-assignment-ids", "assessmentEmphasis", List.of("safetyFlags", "validationResult", "reasonCodes"));
        };
    }
}
