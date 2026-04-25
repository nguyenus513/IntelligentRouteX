package com.routechain.v2.routing;

public interface RoutingProvider {
    String providerId();

    default boolean ready() {
        return true;
    }

    RoutingSnapResult snap(RouteStop stop);

    RoutingRouteResult route(BestPathRequest request);
}
