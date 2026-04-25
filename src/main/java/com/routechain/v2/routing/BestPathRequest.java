package com.routechain.v2.routing;

public record BestPathRequest(
        RouteStop fromStop,
        RouteStop toStop,
        String trafficProfile,
        String weatherClass,
        int timeBucketMinutes,
        String routingIntent) {

    public BestPathRequest(RouteStop fromStop,
                           RouteStop toStop,
                           String trafficProfile,
                           String weatherClass,
                           int timeBucketMinutes) {
        this(fromStop, toStop, trafficProfile, weatherClass, timeBucketMinutes, "pool-enrichment");
    }

    public BestPathRequest {
        routingIntent = routingIntent == null || routingIntent.isBlank() ? "pool-enrichment" : routingIntent;
    }
}
