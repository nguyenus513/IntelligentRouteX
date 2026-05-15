package com.routechain.v2.unified;

import com.routechain.v2.DispatchV2CompatibleCore;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.coverage.CoverageDrainOrchestrator;
import com.routechain.v2.coverage.CoverageDrainResult;

import java.util.LinkedHashMap;
import java.util.Map;

public final class UnifiedDispatchCore {
    private final CoverageDrainOrchestrator coverageDrainOrchestrator;

    public UnifiedDispatchCore(DispatchV2CompatibleCore dispatchCore) {
        this.coverageDrainOrchestrator = new CoverageDrainOrchestrator(dispatchCore);
    }

    public UnifiedDispatchResult dispatch(UnifiedDispatchRequest request) {
        DispatchV2Request v2Request = new DispatchV2Request(
                "dispatch-v2-request/v1",
                request.traceId(),
                request.orders(),
                request.drivers(),
                request.regions(),
                request.weatherProfile(),
                request.decisionTime());
        CoverageDrainResult drain = coverageDrainOrchestrator.drain(v2Request, request.strategy(), request.policy());
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("coverageMode", request.policy().coverageMode().name());
        diagnostics.put("dispatchMode", request.mode().name());
        diagnostics.put("dispatchStrategy", request.strategy().name());
        diagnostics.put("passCount", drain.passTimeline().size());
        diagnostics.put("passTimeline", drain.passTimeline());
        diagnostics.put("coverageSummary", drain.coverageSummary());
        diagnostics.put("driverLoadSummary", drain.driverLoadSummary());
        diagnostics.put("accountingInvariant", Map.of(
                "inputOrderCount", drain.coverageSummary().inputOrderCount(),
                "assignedOrderCount", drain.coverageSummary().assignedOrderCount(),
                "deferredOrderCount", drain.coverageSummary().deferredOrderCount(),
                "rejectedOrderCount", drain.coverageSummary().rejectedOrderCount(),
                "uncoveredOrderCount", drain.coverageSummary().uncoveredOrderCount(),
                "duplicateAssignedOrderCount", drain.coverageSummary().duplicateAssignedOrderCount(),
                "accountedOrderCount", drain.coverageSummary().accountedOrderCount(),
                "accountingInvariantPassed", drain.coverageSummary().accountingInvariantPassed()));
        return new UnifiedDispatchResult(
                "unified-dispatch-result/v1",
                request.traceId(),
                request.mode(),
                request.strategy(),
                drain.dispatchResult(),
                drain.coverageSummary(),
                drain.passTimeline(),
                drain.driverLoadSummary(),
                diagnostics);
    }
}
