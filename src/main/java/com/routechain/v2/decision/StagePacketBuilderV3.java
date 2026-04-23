package com.routechain.v2.decision;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class StagePacketBuilderV3 {
    private final StageBudgetPolicy budgetPolicy = new StageBudgetPolicy();
    private final StageObjectivePolicy objectivePolicy = new StageObjectivePolicy();
    private final StageVisibilityPolicy visibilityPolicy = new StageVisibilityPolicy();
    private final DecisionSessionStore sessionStore;

    StagePacketBuilderV3(DecisionSessionStore sessionStore) {
        this.sessionStore = sessionStore;
    }

    StagePacketBuildResult build(DecisionStageInputV1 input, StagePromptSpec spec) {
        List<Map<String, Object>> limitedRows = budgetPolicy.limitedWindow(input.stageName(), input.candidateSet());
        Map<String, Object> candidateWindow = visibilityPolicy.candidateWindow(input, limitedRows);
        Map<String, Object> comparisonPack = visibilityPolicy.comparisonPack(input);
        Map<String, Object> geospatialContext = visibilityPolicy.geospatialContext(input);
        DecisionSessionStore.SessionContext sessionContext = sessionStore.resolveContext(input);
        Map<String, Object> packet = new LinkedHashMap<>();
        packet.put("schemaVersion", "decision-stage-packet/v3");
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
        packet.put("sessionRefs", sessionContext.sessionRefs());
        return new StagePacketBuildResult(
                Map.copyOf(packet),
                visibilityPolicy.candidateCount(candidateWindow),
                visibilityPolicy.comparisonPackCoverage(input.stageName(), comparisonPack),
                visibilityPolicy.geospatialCoverage(input.stageName(), geospatialContext),
                visibilityPolicy.missingContextFlags(input, comparisonPack, geospatialContext, candidateWindow),
                sessionContext.sessionRefCount());
    }

    record StagePacketBuildResult(
            Map<String, Object> packet,
            int candidateCountSeen,
            double comparisonPackCoverage,
            double geospatialCoverage,
            List<String> missingContextFlags,
            int sessionRefCount) {
    }
}
