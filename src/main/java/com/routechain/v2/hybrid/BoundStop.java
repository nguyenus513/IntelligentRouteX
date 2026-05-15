package com.routechain.v2.hybrid;

import com.routechain.domain.GeoPoint;

public record BoundStop(String stopId, String orderId, StopType type, GeoPoint location) {
}
