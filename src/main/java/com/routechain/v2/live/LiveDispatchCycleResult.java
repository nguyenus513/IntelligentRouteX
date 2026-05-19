package com.routechain.v2.live;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record LiveDispatchCycleResult(
        String cycleId,
        int cycle,
        int assigned,
        int buffered,
        List<String> frozenStopIds,
        List<LiveRouteSnapshot> routes,
        Map<String, Object> diagnostics,
        Instant completedAt) {
}
