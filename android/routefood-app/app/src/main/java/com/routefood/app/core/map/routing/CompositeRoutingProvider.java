package com.routefood.app.core.map.routing;

import com.routefood.app.data.model.GeoPoint;

import java.util.List;

public class CompositeRoutingProvider implements RoutingProvider {
    private final RoutingProvider primary;
    private final RoutingProvider fallback;

    public CompositeRoutingProvider(RoutingProvider primary, RoutingProvider fallback) {
        this.primary = primary;
        this.fallback = fallback;
    }

    @Override
    public RoadRoute routeFixedOrder(List<GeoPoint> rawWaypoints) throws Exception {
        try {
            return primary.routeFixedOrder(rawWaypoints);
        } catch (Exception primaryError) {
            return fallback.routeFixedOrder(rawWaypoints);
        }
    }
}
