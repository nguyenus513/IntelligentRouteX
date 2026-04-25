package com.routechain.v2.routing;

import java.util.List;

public final class SyntheticRoutingProvider implements RoutingProvider {
    private final BestPathRouter bestPathRouter;

    public SyntheticRoutingProvider(BestPathRouter bestPathRouter) {
        this.bestPathRouter = bestPathRouter;
    }

    @Override
    public String providerId() {
        return "synthetic";
    }

    @Override
    public RoutingSnapResult snap(RouteStop stop) {
        return new RoutingSnapResult(
                "routing-snap-result/v1",
                providerId(),
                "SYNTHETIC_IDENTITY",
                stop.latitude(),
                stop.longitude(),
                stop.latitude(),
                stop.longitude(),
                0.0,
                1.0,
                stop.stopId(),
                stop.stopId(),
                List.of("synthetic-snap-identity"));
    }

    @Override
    public RoutingRouteResult route(BestPathRequest request) {
        BestPathResult result = bestPathRouter.route(request);
        List<RoutePolylinePoint> polyline = List.of(
                new RoutePolylinePoint(request.fromStop().latitude(), request.fromStop().longitude(), "from"),
                new RoutePolylinePoint(request.toStop().latitude(), request.toStop().longitude(), "to"));
        LegRouteVector leg = result.legVector().withRoutingGeometry(providerId(), "synthetic-straight-line", polyline, "synthetic-routing-provider");
        return new RoutingRouteResult(
                "routing-route-result/v1",
                providerId(),
                "synthetic-straight-line",
                leg,
                result.corridorPreferenceScore(),
                polyline,
                List.of("synthetic-routing-provider"));
    }
}
