package com.routechain.v2.improvement;

import com.routechain.v2.hybrid.BoundRoute;
import com.routechain.v2.hybrid.MoveEvaluationTrace;

import java.util.List;

public record MoveEvaluationResult(
        boolean accepted,
        BoundRoute fromRoute,
        BoundRoute toRoute,
        double oldKm,
        double newKm,
        long oldLateCount,
        long newLateCount,
        double oldTotalLatenessMinutes,
        double newTotalLatenessMinutes,
        List<MoveEvaluationTrace> traces,
        SearchCacheStats cacheStats) {

    public MoveEvaluationResult {
        traces = traces == null ? List.of() : List.copyOf(traces);
        cacheStats = cacheStats == null ? new SearchCacheStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) : cacheStats;
    }
}
