package com.routechain.v2.objective;

public record QualityCost(
        double orderToDeliveryCost,
        double latenessP95Cost,
        double latenessP99Cost,
        double freshnessCost,
        double pickupWaitCost,
        double detourCost,
        double routeBeautyCost) {

    public double total() {
        return orderToDeliveryCost
                + latenessP95Cost
                + latenessP99Cost
                + freshnessCost
                + pickupWaitCost
                + detourCost
                + routeBeautyCost;
    }
}
