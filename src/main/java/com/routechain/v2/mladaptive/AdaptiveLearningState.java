package com.routechain.v2.mladaptive;

import com.routechain.v2.hybrid.CandidateSource;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class AdaptiveLearningState {
    private final Map<String, Double> seedRewards = new LinkedHashMap<>();
    private final Map<String, Double> operatorRewards = new LinkedHashMap<>();
    private final Map<String, Double> movePatternRewards = new LinkedHashMap<>();

    public AdaptiveLearningState() {
        for (CandidateSource source : CandidateSource.values()) {
            seedRewards.put(source.name(), 0.0);
        }
        for (String operator : List.of("EXACT_REORDER", "TWO_OPT", "OR_OPT", "RELOCATE", "SWAP", "SWAP_STAR", "CROSS_INSERTION", "REGRET_REPAIR", "ALNS_DESTROY_REPAIR")) {
            operatorRewards.put(operator, 0.0);
        }
    }

    public double seedReward(CandidateSource source) {
        return seedRewards.getOrDefault(source == null ? "UNKNOWN" : source.name(), 0.0);
    }

    public double operatorReward(String operator) {
        return operatorRewards.getOrDefault(normalizeOperator(operator), 0.0);
    }

    public double movePatternReward(MovePatternKey key) {
        return key == null ? 0.0 : movePatternRewards.getOrDefault(key.key(), 0.0);
    }

    public void updateSeed(CandidateSource source, double reward) {
        if (source != null) {
            seedRewards.merge(source.name(), reward, AdaptiveLearningState::smooth);
        }
    }

    public void updateOperator(String operator, double reward) {
        operatorRewards.merge(normalizeOperator(operator), reward, AdaptiveLearningState::smooth);
    }

    public void updateMovePattern(MovePatternKey key, double reward) {
        if (key != null) {
            movePatternRewards.merge(key.key(), reward, AdaptiveLearningState::smooth);
        }
    }

    public Map<String, Double> seedRewards() {
        return Map.copyOf(seedRewards);
    }

    public Map<String, Double> operatorRewards() {
        return Map.copyOf(operatorRewards);
    }

    public Map<String, Double> movePatternRewards() {
        return Map.copyOf(movePatternRewards);
    }

    public void replace(Map<String, Double> nextSeedRewards,
                        Map<String, Double> nextOperatorRewards,
                        Map<String, Double> nextMovePatternRewards) {
        if (nextSeedRewards != null) {
            seedRewards.putAll(nextSeedRewards);
        }
        if (nextOperatorRewards != null) {
            operatorRewards.putAll(nextOperatorRewards);
        }
        if (nextMovePatternRewards != null) {
            movePatternRewards.clear();
            movePatternRewards.putAll(nextMovePatternRewards);
        }
    }

    private static double smooth(double oldValue, double reward) {
        return round((oldValue * 0.8) + (reward * 0.2));
    }

    private static String normalizeOperator(String operator) {
        if (operator == null || operator.isBlank()) {
            return "UNKNOWN";
        }
        return operator.trim().toUpperCase().replace('-', '_');
    }

    private static double round(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }
}
