package com.routechain.v2.coverage;

import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.quota.DriverLoadSummary;

import java.util.List;

public record CoverageDrainResult(
        DispatchV2Result dispatchResult,
        CoverageSummary coverageSummary,
        List<PassSummary> passTimeline,
        List<DriverLoadSummary> driverLoadSummary) {
}
