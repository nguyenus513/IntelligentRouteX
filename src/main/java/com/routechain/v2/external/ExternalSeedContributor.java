package com.routechain.v2.external;

import com.routechain.v2.routing.DistanceDurationMatrixSnapshot;
import com.routechain.v2.unified.UnifiedDispatchRequest;

public interface ExternalSeedContributor {
    String contributorId();

    ExternalSeedContribution contribute(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot);
}
