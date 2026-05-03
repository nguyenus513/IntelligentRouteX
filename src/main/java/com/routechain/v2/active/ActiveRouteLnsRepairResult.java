package com.routechain.v2.active;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record ActiveRouteLnsRepairResult(
        String schemaVersion,
        List<ActiveRouteInsertionCandidate> candidates,
        int operatorsTried,
        int acceptedCandidates,
        List<String> operatorNames,
        List<String> degradeReasons) implements SchemaVersioned {

    public ActiveRouteLnsRepairResult {
        candidates = candidates == null ? List.of() : List.copyOf(candidates);
        operatorNames = operatorNames == null ? List.of() : List.copyOf(operatorNames);
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }
}
