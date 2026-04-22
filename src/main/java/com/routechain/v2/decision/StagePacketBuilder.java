package com.routechain.v2.decision;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class StagePacketBuilder {
    private final StageBudgetPolicy budgetPolicy = new StageBudgetPolicy();
    private final StageObjectivePolicy objectivePolicy = new StageObjectivePolicy();
    private final StageVisibilityPolicy visibilityPolicy = new StageVisibilityPolicy();

    StagePacketBuildResult build(DecisionStageInputV1 input, StagePromptSpec spec) {
        List<Map<String, Object>> limitedRows = budgetPolicy.limitedWindow(input.stageName(), input.candidateSet());
        Map<String, Object> candidateWindow = visibilityPolicy.candidateWindow(input, limitedRows);
        Map<String, Object> comparisonPack = visibilityPolicy.comparisonPack(input);
        Map<String, Object> geospatialContext = visibilityPolicy.geospatialContext(input);
        Map<String, Object> packet = new LinkedHashMap<>();
        packet.put("schemaVersion", "decision-stage-packet/v2");
        packet.put("traceId", input.traceId());
        packet.put("runId", input.runId());
        packet.put("tickId", input.tickId());
        packet.put("stageName", input.stageName().wireName());
        packet.put("task", Map.of(
                "mission", spec.mission(),
                "mustDo", spec.mustDo(),
                "mustNotDo", spec.mustNotDo()));
        packet.put("dispatchContext", visibilityPolicy.dispatchContext(input));
        packet.put("candidateWindow", candidateWindow);
        packet.put("referenceFrame", visibilityPolicy.referenceFrame(input));
        packet.put("comparisonPack", comparisonPack);
        packet.put("geospatialContext", geospatialContext);
        packet.put("upstreamSummary", visibilityPolicy.upstreamSummary(input));
        packet.put("constraints", visibilityPolicy.constraints(input));
        packet.put("objectiveWeights", visibilityPolicy.objectiveWeights(input));
        packet.put("outputRequirements", objectivePolicy.outputRequirementsFor(input.stageName()));
        packet.put("budget", budgetPolicy.appliedBudget(input.stageName(), visibilityPolicy.candidateCount(candidateWindow)));
        return new StagePacketBuildResult(
                Map.copyOf(packet),
                visibilityPolicy.candidateCount(candidateWindow),
                visibilityPolicy.comparisonPackCoverage(input.stageName(), comparisonPack),
                visibilityPolicy.geospatialCoverage(input.stageName(), geospatialContext),
                visibilityPolicy.missingContextFlags(input, comparisonPack, geospatialContext, candidateWindow));
    }

    StagePromptSpec stageSpec(PromptSpecManifest manifest, DecisionStageName stageName) {
        PromptSpecManifest.StagePromptResourceEntry entry = manifest.stageMappings().get(stageName.wireName());
        if (entry == null) {
            throw new IllegalStateException("Missing stage prompt mapping for " + stageName.wireName());
        }
        return new StagePromptSpec(
                stageName,
                manifest.promptSpecVersion(),
                manifest.packetTemplateVersion(),
                stageName.wireName(),
                entry.systemPrompt(),
                entry.packetTemplate(),
                objectivePolicy.missionFor(stageName),
                objectivePolicy.mustDoFor(stageName),
                objectivePolicy.mustNotDoFor(stageName),
                objectivePolicy.allowedInputsFor(stageName),
                objectivePolicy.objectiveFor(stageName),
                budgetPolicy.budgetFor(stageName),
                comparisonLens(stageName),
                geospatialLens(stageName),
                visibilityPolicy.visibilityProfile(stageName),
                multiPassEnabled(stageName),
                List.of(
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

    List<String> allowedTools(DecisionStageName stageName) {
        return visibilityPolicy.allowedTools(stageName);
    }

    private ComparisonLens comparisonLens(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> ComparisonLens.OBSERVATION_NORMALIZATION_LENS;
            case PAIR_BUNDLE -> ComparisonLens.PAIR_SUPPORT_LENS;
            case ANCHOR -> ComparisonLens.ANCHOR_STABILITY_LENS;
            case DRIVER -> ComparisonLens.DRIVER_FIT_LENS;
            case ROUTE_GENERATION -> ComparisonLens.ROUTE_FEASIBILITY_LENS;
            case ROUTE_CRITIQUE -> ComparisonLens.ROUTE_DOMINANCE_LENS;
            case SCENARIO -> ComparisonLens.SCENARIO_ROBUSTNESS_LENS;
            case FINAL_SELECTION -> ComparisonLens.GLOBAL_SELECTION_LENS;
            case SAFETY_EXECUTE -> ComparisonLens.EXECUTION_SAFETY_LENS;
        };
    }

    private GeospatialLens geospatialLens(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> GeospatialLens.WORLD_STATE_LENS;
            case PAIR_BUNDLE -> GeospatialLens.BUNDLE_GEOMETRY_LENS;
            case ANCHOR -> GeospatialLens.ANCHOR_AREA_LENS;
            case DRIVER -> GeospatialLens.DRIVER_CORRIDOR_ENTRY_LENS;
            case ROUTE_GENERATION -> GeospatialLens.ROUTE_CORRIDOR_LENS;
            case ROUTE_CRITIQUE -> GeospatialLens.ROUTE_DOMINANCE_GEO_LENS;
            case SCENARIO -> GeospatialLens.SCENARIO_OVERLAY_LENS;
            case FINAL_SELECTION -> GeospatialLens.FINAL_CONFLICT_GEO_LENS;
            case SAFETY_EXECUTE -> GeospatialLens.EXECUTION_VALIDATION_LENS;
        };
    }

    private boolean multiPassEnabled(DecisionStageName stageName) {
        return switch (stageName) {
            case DRIVER, ROUTE_GENERATION, ROUTE_CRITIQUE, SCENARIO, FINAL_SELECTION -> true;
            case OBSERVATION_PACK, PAIR_BUNDLE, ANCHOR, SAFETY_EXECUTE -> false;
        };
    }

    record StagePacketBuildResult(
            Map<String, Object> packet,
            int candidateCountSeen,
            double comparisonPackCoverage,
            double geospatialCoverage,
            List<String> missingContextFlags) {
    }
}
