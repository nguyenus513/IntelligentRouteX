package com.routefood.app.core.map.routing;

import com.routefood.app.core.map.OsrmRouteClient;
import com.routefood.app.data.model.GeoPoint;

import java.util.ArrayList;
import java.util.List;

public class OsrmRoutingProvider implements RoutingProvider {
    private static final double FIRST_POINT_TOLERANCE_METERS = 40.0;
    private final OsrmRouteClient routeClient;

    public OsrmRoutingProvider() {
        this(new OsrmRouteClient());
    }

    public OsrmRoutingProvider(String baseUrl) {
        this(new OsrmRouteClient(baseUrl));
    }

    public OsrmRoutingProvider(OsrmRouteClient routeClient) {
        this.routeClient = routeClient;
    }

    @Override
    public RoadRoute routeFixedOrder(List<GeoPoint> rawWaypoints) throws Exception {
        OsrmRouteClient.NavigationRouteResult result = routeClient.routeWaypointsNavigationBlocking(rawWaypoints);
        RouteQuality quality = buildQuality(result);
        return new RoadRoute(
                "osrm_fixed_order_v2",
                result.geometry.size() >= 2,
                result.geometry,
                result.instructions,
                result.waypoints,
                result.distanceMeters,
                result.durationSeconds,
                result.legDistanceMeters,
                quality
        );
    }

    private RouteQuality buildQuality(OsrmRouteClient.NavigationRouteResult result) {
        List<String> warnings = new ArrayList<>();
        boolean firstPointMatchesDriver = false;
        if (!result.geometry.isEmpty() && !result.waypoints.isEmpty()) {
            double firstDistance = distanceMeters(result.geometry.get(0), result.waypoints.get(0).snapped);
            firstPointMatchesDriver = firstDistance <= FIRST_POINT_TOLERANCE_METERS;
            if (!firstPointMatchesDriver) {
                warnings.add("First geometry point is " + Math.round(firstDistance) + "m from snapped driver point");
            }
        }
        if (result.maxSnapDistanceMeters > 80.0) {
            warnings.add("Max snap distance warning: " + Math.round(result.maxSnapDistanceMeters) + "m");
        }
        return new RouteQuality(
                "osrm",
                result.maxSnapDistanceMeters,
                firstPointMatchesDriver,
                true,
                warnings
        );
    }

    private double distanceMeters(GeoPoint a, GeoPoint b) {
        double latMeters = (a.latitude() - b.latitude()) * 111_320.0;
        double lngMeters = (a.longitude() - b.longitude()) * 111_320.0 * Math.cos(Math.toRadians((a.latitude() + b.latitude()) / 2.0));
        return Math.sqrt((latMeters * latMeters) + (lngMeters * lngMeters));
    }
}
