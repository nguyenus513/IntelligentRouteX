package com.routefood.app.core.map.routing;

import com.routefood.app.core.map.OsrmRouteClient;
import com.routefood.app.data.model.GeoPoint;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class RoadRoute {
    public final String provider;
    public final boolean geometryAvailable;
    public final List<GeoPoint> coordinates;
    public final List<OsrmRouteClient.NavigationInstruction> instructions;
    public final List<OsrmRouteClient.SnappedWaypoint> snappedWaypoints;
    public final double distanceMeters;
    public final double durationSeconds;
    public final List<Double> legDistanceMeters;
    public final RouteQuality quality;

    public RoadRoute(
            String provider,
            boolean geometryAvailable,
            List<GeoPoint> coordinates,
            List<OsrmRouteClient.NavigationInstruction> instructions,
            List<OsrmRouteClient.SnappedWaypoint> snappedWaypoints,
            double distanceMeters,
            double durationSeconds,
            RouteQuality quality
    ) {
        this(provider, geometryAvailable, coordinates, instructions, snappedWaypoints, distanceMeters, durationSeconds, Collections.emptyList(), quality);
    }

    public RoadRoute(
            String provider,
            boolean geometryAvailable,
            List<GeoPoint> coordinates,
            List<OsrmRouteClient.NavigationInstruction> instructions,
            List<OsrmRouteClient.SnappedWaypoint> snappedWaypoints,
            double distanceMeters,
            double durationSeconds,
            List<Double> legDistanceMeters,
            RouteQuality quality
    ) {
        this.provider = provider;
        this.geometryAvailable = geometryAvailable;
        this.coordinates = Collections.unmodifiableList(new ArrayList<>(coordinates));
        this.instructions = Collections.unmodifiableList(new ArrayList<>(instructions));
        this.snappedWaypoints = Collections.unmodifiableList(new ArrayList<>(snappedWaypoints));
        this.distanceMeters = distanceMeters;
        this.durationSeconds = durationSeconds;
        this.legDistanceMeters = Collections.unmodifiableList(new ArrayList<>(legDistanceMeters));
        this.quality = quality;
    }
}
