package com.routechain.v2.external;

import com.routechain.v2.routing.DistanceDurationMatrixSnapshot;
import com.routechain.v2.unified.UnifiedDispatchRequest;

import java.util.Map;

public final class VroomSeedContributor implements ExternalSeedContributor {
    @Override
    public String contributorId() {
        return "VROOM";
    }

    @Override
    public ExternalSeedContribution contribute(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot) {
        return new ExternalSeedContribution(
                contributorId(),
                ExternalContributorStatus.EVIDENCE_GAP,
                null,
                "vroom-runtime-not-configured",
                Map.of("expectedSource", "VROOM_SEED"));
    }
}
