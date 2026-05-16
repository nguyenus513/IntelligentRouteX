package com.routechain.v2.external;

import java.util.Map;

public record ExternalSolverAvailability(
        String solverId,
        ExternalContributorStatus status,
        String reason,
        String version,
        Map<String, Object> diagnostics) {

    public ExternalSolverAvailability {
        status = status == null ? ExternalContributorStatus.EVIDENCE_GAP : status;
        diagnostics = diagnostics == null ? Map.of() : Map.copyOf(diagnostics);
    }
}
