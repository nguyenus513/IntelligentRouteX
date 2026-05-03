package com.routechain.v2.objective;

public record FairnessCost(
        double driverUtilizationCost,
        double routeChurnCost) {

    public double total() {
        return driverUtilizationCost + routeChurnCost;
    }
}
