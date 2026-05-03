package com.routechain.v2.repair;

public final class RepairAcceptancePolicy {
    public boolean accept(RepairCandidate incumbent, RepairCandidate challenger) {
        return accept(incumbent, challenger, Double.NEGATIVE_INFINITY);
    }

    public boolean accept(RepairCandidate incumbent, RepairCandidate challenger, double baselineScore) {
        if (challenger == null || !challenger.feasible()) {
            return false;
        }
        if (challenger.reasons().stream().anyMatch(reason -> reason.contains("frozen-prefix"))) {
            return false;
        }
        if (challenger.insertionCandidate().freshnessRisk() > 0.85 || challenger.insertionCandidate().churnRisk() > 0.75) {
            return false;
        }
        if (challenger.objectiveScore() <= baselineScore + 1e-9) {
            return false;
        }
        return incumbent == null || !incumbent.feasible() || challenger.objectiveScore() > incumbent.objectiveScore() + 1e-9;
    }
}
