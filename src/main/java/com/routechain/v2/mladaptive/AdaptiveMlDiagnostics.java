package com.routechain.v2.mladaptive;

import java.util.Map;

public record AdaptiveMlDiagnostics(
        boolean enabled,
        String mode,
        Map<String, Object> adaptiveSeedPolicy,
        Map<String, Object> adaptiveOperatorPolicy,
        Map<String, Object> adaptiveMovePriority,
        Map<String, Object> rewardUpdate,
        Map<String, Double> seedRewardsAfter,
        Map<String, Double> operatorRewardsAfter,
        Map<String, Double> movePatternRewardsAfter) {
}
