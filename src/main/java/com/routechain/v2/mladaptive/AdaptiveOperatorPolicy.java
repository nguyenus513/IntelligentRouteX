package com.routechain.v2.mladaptive;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class AdaptiveOperatorPolicy {
    private static final List<String> STATIC_ORDER = List.of("EXACT_REORDER", "RELOCATE", "SWAP", "CROSS_INSERTION", "SWAP_STAR");

    public Decision order(AdaptiveLearningState state, double explorationRate) {
        List<String> ordered = STATIC_ORDER.stream()
                .sorted(Comparator.comparingDouble((String operator) -> state.operatorReward(operator)).reversed())
                .toList();
        Map<String, Double> rewards = new LinkedHashMap<>();
        for (String operator : STATIC_ORDER) {
            rewards.put(operator, state.operatorReward(operator));
        }
        return new Decision(ordered, Math.max(0.0, Math.min(1.0, explorationRate)), rewards);
    }

    public record Decision(List<String> operatorOrder, double explorationRate, Map<String, Double> operatorRewardsBefore) {
    }
}
