package com.routechain.v2.routing;

public record PickupDeliveryStop(
        String stopId,
        String orderId,
        StopKind kind,
        RouteStop routeStop) {

    public PickupDeliveryStop {
        if (stopId == null || stopId.isBlank()) {
            throw new IllegalArgumentException("stopId is required");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (kind == null) {
            throw new IllegalArgumentException("kind is required");
        }
        if (routeStop == null) {
            throw new IllegalArgumentException("routeStop is required");
        }
    }

    public static PickupDeliveryStop pickup(String orderId, RouteStop routeStop) {
        return new PickupDeliveryStop(orderId + ":pickup", orderId, StopKind.PICKUP, routeStop);
    }

    public static PickupDeliveryStop dropoff(String orderId, RouteStop routeStop) {
        return new PickupDeliveryStop(orderId + ":dropoff", orderId, StopKind.DROPOFF, routeStop);
    }

    public enum StopKind {
        PICKUP,
        DROPOFF
    }
}
