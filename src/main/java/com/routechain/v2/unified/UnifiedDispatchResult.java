package com.routechain.v2.unified;

import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.coverage.CoverageSummary;
import com.routechain.v2.coverage.PassSummary;
import com.routechain.v2.quota.DriverLoadSummary;

import java.util.List;
import java.util.Map;

public record UnifiedDispatchResult(
        String schemaVersion,
        String traceId,
        DispatchMode mode,
        DispatchStrategy strategy,
        DispatchV2Result dispatchResult,
        CoverageSummary coverageSummary,
        List<PassSummary> passTimeline,
        List<DriverLoadSummary> driverLoadSummary,
        Map<String, Object> diagnostics) {

    public UnifiedDispatchResult {
        schemaVersion = schemaVersion == null ? "unified-dispatch-result/v1" : schemaVersion;
        passTimeline = passTimeline == null ? List.of() : List.copyOf(passTimeline);
        driverLoadSummary = driverLoadSummary == null ? List.of() : List.copyOf(driverLoadSummary);
        diagnostics = diagnostics == null ? Map.of() : Map.copyOf(diagnostics);
    }
}
