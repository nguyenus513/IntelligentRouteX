package com.routechain.v2.active;

import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.v2.SchemaVersioned;

public record ActiveRouteStop(
        String schemaVersion,
        String orderId,
        ActiveRouteStopType stopType,
        GeoPoint location) implements SchemaVersioned {

    public static ActiveRouteStop pickup(Order order) {
        return new ActiveRouteStop("active-route-stop/v1", order.orderId(), ActiveRouteStopType.PICKUP, order.pickupPoint());
    }

    public static ActiveRouteStop dropoff(Order order) {
        return new ActiveRouteStop("active-route-stop/v1", order.orderId(), ActiveRouteStopType.DROPOFF, order.dropoffPoint());
    }

    public String signature() {
        return stopType.name().charAt(0) + ":" + orderId;
    }
}
