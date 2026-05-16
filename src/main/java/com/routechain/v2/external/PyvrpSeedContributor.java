package com.routechain.v2.external;

import com.routechain.v2.routing.DistanceDurationMatrixSnapshot;
import com.routechain.v2.unified.UnifiedDispatchRequest;

import java.util.Map;

public final class PyvrpSeedContributor implements ExternalSeedContributor {
    @Override
    public String contributorId() {
        return "PYVRP";
    }

    @Override
    public ExternalSeedContribution contribute(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot) {
        return new ExternalSeedContribution(
                contributorId(),
                ExternalContributorStatus.EVIDENCE_GAP,
                null,
                "pyvrp-runtime-not-configured",
                Map.of("expectedSource", "PYVRP_SEED"));
    }
}
