package com.routechain.v2.perf;

import com.routechain.domain.GeoPoint;

import java.util.List;

final class RoadAwareCustomerSampler {
    private final List<GeoPoint> customers = List.of(
            new GeoPoint(10.78118, 106.70752),
            new GeoPoint(10.78234, 106.70912),
            new GeoPoint(10.78352, 106.71076),
            new GeoPoint(10.78466, 106.71238),
            new GeoPoint(10.73384, 106.72806),
            new GeoPoint(10.73516, 106.72958),
            new GeoPoint(10.73644, 106.73102),
            new GeoPoint(10.73774, 106.73254),
            new GeoPoint(10.80902, 106.72156),
            new GeoPoint(10.81024, 106.72318),
            new GeoPoint(10.81152, 106.72472),
            new GeoPoint(10.81282, 106.72630),
            new GeoPoint(10.84510, 106.81516),
            new GeoPoint(10.84642, 106.81676),
            new GeoPoint(10.84776, 106.81832),
            new GeoPoint(10.84904, 106.81992),
            new GeoPoint(10.76634, 106.66528),
            new GeoPoint(10.76766, 106.66684),
            new GeoPoint(10.76892, 106.66842),
            new GeoPoint(10.77020, 106.67002));

    GeoPoint sample(int index) {
        return customers.get(Math.floorMod(index, customers.size()));
    }
}
