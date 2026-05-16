package com.routechain.v2.external;

import com.routechain.v2.hybrid.SolutionSeedCandidate;

import java.util.Map;

public record ExternalSeedContribution(
        String contributorId,
        ExternalContributorStatus status,
        SolutionSeedCandidate seed,
        String reason,
        Map<String, Object> diagnostics) {

    public ExternalSeedContribution {
        status = status == null ? ExternalContributorStatus.EVIDENCE_GAP : status;
        diagnostics = diagnostics == null ? Map.of() : Map.copyOf(diagnostics);
    }
}
