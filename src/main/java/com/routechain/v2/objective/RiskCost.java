package com.routechain.v2.objective;

public record RiskCost(
        double tailRiskCost,
        double cancelNoShowRiskCost,
        double etaUncertaintyCost,
        double readyTimeUncertaintyCost) {

    public double total() {
        return tailRiskCost + cancelNoShowRiskCost + etaUncertaintyCost + readyTimeUncertaintyCost;
    }
}
