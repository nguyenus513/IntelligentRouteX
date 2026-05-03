package com.routechain.v2.objective;

public record ObjectiveContext(
        String regionId,
        String timeOfDayBucket,
        String supplyDemandRegime,
        String trafficCondition) {

    public static ObjectiveContext defaultContext() {
        return new ObjectiveContext("unknown", "unknown", "normal", "normal");
    }
}
