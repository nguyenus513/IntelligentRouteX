package com.routechain.v2.objective;

import java.util.List;

public record ObjectiveBreakdown(
        String schemaVersion,
        HardConstraintReport hard,
        QualityCost quality,
        RiskCost risk,
        FairnessCost fairness,
        RuntimeCost runtime,
        RewardTerm reward,
        double totalCost,
        double totalScore,
        List<String> reasons) {

    public static ObjectiveBreakdown fromScore(double score, boolean feasible, List<String> reasons) {
        HardConstraintReport hard = feasible ? HardConstraintReport.ok() : HardConstraintReport.infeasible(List.of("candidate-marked-infeasible"));
        double qualityCost = Math.max(0.0, 1.0 - score);
        QualityCost quality = new QualityCost(qualityCost, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
        RiskCost risk = new RiskCost(0.0, 0.0, 0.0, 0.0);
        FairnessCost fairness = new FairnessCost(0.0, 0.0);
        RuntimeCost runtime = new RuntimeCost(0.0, 0.0, 0.0);
        RewardTerm reward = new RewardTerm(Math.max(0.0, score - 1.0), 0.0, Math.max(0.0, score));
        return new ObjectiveBreakdown(
                "objective-breakdown/v1",
                hard,
                quality,
                risk,
                fairness,
                runtime,
                reward,
                quality.total() + risk.total() + fairness.total() + runtime.total() - reward.total(),
                feasible ? score : Double.NEGATIVE_INFINITY,
                List.copyOf(reasons));
    }

    public boolean hardFeasible() {
        return hard.feasible();
    }

    public double totalUtility() {
        return totalScore;
    }

    public double qualityCost() {
        return quality.total();
    }

    public double riskCost() {
        return risk.total();
    }

    public double fairnessCost() {
        return fairness.total();
    }

    public double runtimeCost() {
        return runtime.total();
    }

    public double rewardValue() {
        return reward.total();
    }
}
