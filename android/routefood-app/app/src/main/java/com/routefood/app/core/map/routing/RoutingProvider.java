package com.routefood.app.core.map.routing;

import com.routefood.app.data.model.GeoPoint;

import java.util.List;

public interface RoutingProvider {
    RoadRoute routeFixedOrder(List<GeoPoint> rawWaypoints) throws Exception;
}
