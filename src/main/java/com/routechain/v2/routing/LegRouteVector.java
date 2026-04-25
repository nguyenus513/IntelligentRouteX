package com.routechain.v2.routing;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record LegRouteVector(
        String schemaVersion,
        String fromStopId,
        String toStopId,
        double deltaLat,
        double deltaLng,
        double bearingStartDeg,
        double bearingEndDeg,
        double bearingMeanDeg,
        double distanceMeters,
        double travelTimeSeconds,
        double avgSpeedMps,
        double majorRoadRatio,
        double minorRoadRatio,
        int turnCount,
        int leftTurnCount,
        int rightTurnCount,
        int uTurnCount,
        double straightnessScore,
        double congestionScore,
        double roadRiskScore,
        double routeCost,
        String routingProvider,
        String geometryKind,
        List<RoutePolylinePoint> polyline,
        String routingFallbackReason) implements SchemaVersioned {

    public LegRouteVector {
        routingProvider = routingProvider == null || routingProvider.isBlank() ? "synthetic" : routingProvider;
        geometryKind = geometryKind == null || geometryKind.isBlank() ? "synthetic-straight-line" : geometryKind;
        polyline = polyline == null ? List.of() : List.copyOf(polyline);
        routingFallbackReason = routingFallbackReason == null ? "" : routingFallbackReason;
    }

    public LegRouteVector(String schemaVersion,
                          String fromStopId,
                          String toStopId,
                          double deltaLat,
                          double deltaLng,
                          double bearingStartDeg,
                          double bearingEndDeg,
                          double bearingMeanDeg,
                          double distanceMeters,
                          double travelTimeSeconds,
                          double avgSpeedMps,
                          double majorRoadRatio,
                          double minorRoadRatio,
                          int turnCount,
                          int leftTurnCount,
                          int rightTurnCount,
                          int uTurnCount,
                          double straightnessScore,
                          double congestionScore,
                          double roadRiskScore,
                          double routeCost) {
        this(schemaVersion, fromStopId, toStopId, deltaLat, deltaLng, bearingStartDeg, bearingEndDeg, bearingMeanDeg,
                distanceMeters, travelTimeSeconds, avgSpeedMps, majorRoadRatio, minorRoadRatio, turnCount,
                leftTurnCount, rightTurnCount, uTurnCount, straightnessScore, congestionScore, roadRiskScore,
                routeCost, "synthetic", "synthetic-straight-line", List.of(), "synthetic-routing-provider");
    }

    public LegRouteVector withRoutingGeometry(String provider,
                                              String newGeometryKind,
                                              List<RoutePolylinePoint> newPolyline,
                                              String fallbackReason) {
        return new LegRouteVector(
                schemaVersion,
                fromStopId,
                toStopId,
                deltaLat,
                deltaLng,
                bearingStartDeg,
                bearingEndDeg,
                bearingMeanDeg,
                distanceMeters,
                travelTimeSeconds,
                avgSpeedMps,
                majorRoadRatio,
                minorRoadRatio,
                turnCount,
                leftTurnCount,
                rightTurnCount,
                uTurnCount,
                straightnessScore,
                congestionScore,
                roadRiskScore,
                routeCost,
                provider,
                newGeometryKind,
                newPolyline,
                fallbackReason);
    }
}
