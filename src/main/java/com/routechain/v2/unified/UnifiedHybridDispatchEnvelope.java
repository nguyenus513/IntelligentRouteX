package com.routechain.v2.unified;

import com.routechain.v2.hybrid.BaselineDominanceResult;
import com.routechain.v2.hybrid.ImprovedSolutionCandidate;
import com.routechain.v2.hybrid.SolutionSeedCandidate;

import java.util.List;
import java.util.Map;

public record UnifiedHybridDispatchEnvelope(
        String schemaVersion,
        DispatchMode mode,
        UnifiedDispatchObjectiveProfile objectiveProfile,
        UnifiedDispatchRoutingMode routingMode,
        SolutionSeedCandidate bestDistanceSeed,
        SolutionSeedCandidate bestObjectiveSeed,
        SolutionSeedCandidate finalSolution,
        List<ImprovedSolutionCandidate> improvedSolutions,
        BaselineDominanceResult dominanceResult,
        Map<String, Object> diagnostics) {

    public UnifiedHybridDispatchEnvelope {
        schemaVersion = schemaVersion == null ? "unified-hybrid-dispatch-envelope/v1" : schemaVersion;
        mode = mode == null ? DispatchMode.STATIC_FULL_COVERAGE : mode;
        objectiveProfile = objectiveProfile == null ? UnifiedDispatchObjectiveProfile.SLA_STRICT : objectiveProfile;
        routingMode = routingMode == null ? UnifiedDispatchRoutingMode.ROAD_OSRM_BOUNDED : routingMode;
        improvedSolutions = improvedSolutions == null ? List.of() : List.copyOf(improvedSolutions);
        diagnostics = diagnostics == null ? Map.of() : Map.copyOf(diagnostics);
    }
}
