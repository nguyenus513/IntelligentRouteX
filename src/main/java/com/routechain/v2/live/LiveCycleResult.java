package com.routechain.v2.live;

import com.routechain.v2.unified.UnifiedDispatchResult;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record LiveCycleResult(
        String cycleId,
        Instant startedAt,
        Instant completedAt,
        int inputOrderCount,
        int driverCount,
        List<String> assignedOrderIds,
        List<String> deferredOrderIds,
        List<String> expiredOrderIds,
        UnifiedDispatchResult unifiedResult,
        Map<String, Object> diagnostics) {
}
