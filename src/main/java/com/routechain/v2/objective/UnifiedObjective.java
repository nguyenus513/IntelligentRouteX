package com.routechain.v2.objective;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.ArrayList;
import java.util.List;

public final class UnifiedObjective {
    private final ObjectiveNormalizer normalizer = new ObjectiveNormalizer();

    public ObjectiveBreakdown scoreSelectorCandidate(SelectorCandidate candidate) {
        List<String> reasons = new ArrayList<>(candidate.reasons());
        reasons.add("unified-objective-selector-score");
        double routeShapePenalty = routeShapePenalty(candidate);
        double boundaryPenalty = candidate.boundaryCross() ? 0.03 : 0.0;
        double fallbackPenalty = fallbackPenalty(candidate);
        double tailRiskPenalty = tailRiskPenalty(candidate);
        double freshnessPenalty = freshnessPenalty(candidate);
        double coverageReward = coverageReward(candidate);
        double batchingReward = batchingReward(candidate);
        double diversityReward = diversityReward(candidate);
        double routeChurnPenalty = routeChurnPenalty(candidate);
        double baseUtility = normalizer.clamp01(candidate.selectionScore()) * Math.max(1, candidate.orderIds().size());
        double coverageFirstReward = Math.max(1, candidate.orderIds().size()) * 2.0;
        double totalUtility = Math.max(0.0, baseUtility + coverageReward + batchingReward + diversityReward
                + coverageFirstReward
                - routeShapePenalty - boundaryPenalty - fallbackPenalty - tailRiskPenalty - freshnessPenalty - routeChurnPenalty);
        if (tailRiskPenalty > 0.0) {
            reasons.add("objective-tail-risk-penalty");
        }
        if (freshnessPenalty > 0.0) {
            reasons.add("objective-freshness-penalty");
        }
        if (coverageReward > 0.0) {
            reasons.add("objective-coverage-reward");
        }
        if (batchingReward > 0.0) {
            reasons.add("objective-batching-reward");
        }
        if (diversityReward > 0.0) {
            reasons.add("objective-diversity-reward");
        }
        QualityCost quality = new QualityCost(
                Math.max(0.0, 1.0 - baseUtility),
                tailRiskPenalty * 0.45,
                tailRiskPenalty * 0.55,
                freshnessPenalty,
                pickupWaitPenalty(candidate),
                routeShapePenalty,
                routeShapePenalty + boundaryPenalty);
        RiskCost risk = new RiskCost(tailRiskPenalty + freshnessPenalty, fallbackPenalty, etaUncertaintyPenalty(candidate), readyTimeUncertaintyPenalty(candidate));
        FairnessCost fairness = new FairnessCost(0.0, routeChurnPenalty);
        RuntimeCost runtime = new RuntimeCost(0.0, 0.0, Math.min(0.06, Math.max(0, candidate.orderIds().size() - 3) * 0.02));
        RewardTerm reward = new RewardTerm(batchingReward, diversityReward, coverageReward);
        double totalCost = quality.total() + risk.total() + fairness.total() + runtime.total() - reward.total() - coverageFirstReward;
        return new ObjectiveBreakdown(
                "objective-breakdown/v1",
                candidate.feasible() ? HardConstraintReport.ok() : HardConstraintReport.infeasible(List.of("candidate-marked-infeasible")),
                quality,
                risk,
                fairness,
                runtime,
                reward,
                totalCost,
                candidate.feasible() ? totalUtility : Double.NEGATIVE_INFINITY,
                reasons.stream().distinct().toList());
    }

    private double coverageReward(SelectorCandidate candidate) {
        return Math.min(0.18, Math.max(0, candidate.orderIds().size() - 1) * 0.06);
    }

    private double batchingReward(SelectorCandidate candidate) {
        if (candidate.orderIds().size() <= 1) {
            return 0.0;
        }
        return Math.min(0.12, 0.04 * (candidate.orderIds().size() - 1));
    }

    private double diversityReward(SelectorCandidate candidate) {
        return candidate.source() == com.routechain.v2.route.RouteProposalSource.ACTIVE_ROUTE_INSERTION ? 0.04 : 0.0;
    }

    private double routeShapePenalty(SelectorCandidate candidate) {
        double penalty = candidate.reasons().contains("selector-route-shape-penalty-applied") ? 0.05 : 0.0;
        if (candidate.reasons().contains("selector-detour-guard-active")) {
            penalty += 0.06;
        }
        return penalty;
    }

    private double fallbackPenalty(SelectorCandidate candidate) {
        double penalty = candidate.degradeReasons().isEmpty() ? 0.0 : 0.02;
        if (candidate.source() == com.routechain.v2.route.RouteProposalSource.FALLBACK_SIMPLE) {
            penalty += 0.06;
        }
        return penalty;
    }

    private double tailRiskPenalty(SelectorCandidate candidate) {
        return candidate.reasons().stream().anyMatch(reason -> reason.contains("urgent") || reason.contains("late") || reason.contains("risk"))
                ? 0.10
                : 0.0;
    }

    private double freshnessPenalty(SelectorCandidate candidate) {
        return candidate.degradeReasons().stream().anyMatch(reason -> reason.contains("food-on-vehicle") || reason.contains("freshness"))
                ? 5.0
                : 0.0;
    }

    private double pickupWaitPenalty(SelectorCandidate candidate) {
        return candidate.reasons().stream().anyMatch(reason -> reason.contains("pickup-wait")) ? 0.07 : 0.0;
    }

    private double etaUncertaintyPenalty(SelectorCandidate candidate) {
        return candidate.degradeReasons().stream().anyMatch(reason -> reason.contains("eta") || reason.contains("timeout")) ? 0.04 : 0.0;
    }

    private double readyTimeUncertaintyPenalty(SelectorCandidate candidate) {
        return candidate.reasons().stream().anyMatch(reason -> reason.contains("ready")) ? 0.04 : 0.0;
    }

    private double routeChurnPenalty(SelectorCandidate candidate) {
        return candidate.source() == com.routechain.v2.route.RouteProposalSource.ACTIVE_ROUTE_INSERTION
                && candidate.degradeReasons().stream().anyMatch(reason -> reason.contains("churn") || reason.contains("frozen"))
                ? 0.12
                : 0.0;
    }
}
