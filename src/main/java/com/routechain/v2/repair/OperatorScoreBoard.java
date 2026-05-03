package com.routechain.v2.repair;

import java.util.EnumMap;
import java.util.Map;

public final class OperatorScoreBoard {
    private final Map<DestroyOperator, Double> destroyScores = new EnumMap<>(DestroyOperator.class);
    private final Map<RepairOperator, Double> repairScores = new EnumMap<>(RepairOperator.class);

    public void reward(DestroyOperator operator, double delta) {
        destroyScores.merge(operator, delta, Double::sum);
    }

    public void reward(RepairOperator operator, double delta) {
        repairScores.merge(operator, delta, Double::sum);
    }

    public Map<DestroyOperator, Double> destroyScores() {
        return Map.copyOf(destroyScores);
    }

    public Map<RepairOperator, Double> repairScores() {
        return Map.copyOf(repairScores);
    }
}
