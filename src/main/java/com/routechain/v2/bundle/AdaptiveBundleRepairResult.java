package com.routechain.v2.bundle;

import com.routechain.v2.repair.ActiveRouteRepairResult;

import java.util.List;
import java.util.Map;

public record AdaptiveBundleRepairResult(
        List<BundleCandidate> riskyBundles,
        ActiveRouteRepairResult repairResult,
        Map<String, Object> feedbackSummary) {

    public AdaptiveBundleRepairResult {
        riskyBundles = riskyBundles == null ? List.of() : List.copyOf(riskyBundles);
        repairResult = repairResult == null ? ActiveRouteRepairResult.empty() : repairResult;
        feedbackSummary = feedbackSummary == null ? Map.of() : Map.copyOf(feedbackSummary);
    }
}
