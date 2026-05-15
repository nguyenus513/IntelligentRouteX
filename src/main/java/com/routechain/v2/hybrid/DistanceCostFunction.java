package com.routechain.v2.hybrid;

@FunctionalInterface
public interface DistanceCostFunction {
    double distanceKm(String legId, double fromLat, double fromLng, double toLat, double toLng);
}
