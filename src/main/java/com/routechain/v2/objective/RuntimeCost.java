package com.routechain.v2.objective;

public record RuntimeCost(
        double stageRuntimeCost,
        double solverBudgetCost,
        double candidateComplexityCost) {

    public double total() {
        return stageRuntimeCost + solverBudgetCost + candidateComplexityCost;
    }
}
