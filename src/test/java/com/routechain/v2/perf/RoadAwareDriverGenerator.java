package com.routechain.v2.perf;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;

import java.util.ArrayList;
import java.util.List;

final class RoadAwareDriverGenerator {
    private static final List<GeoPoint> STARTS = List.of(
            new GeoPoint(10.77478, 106.69918),
            new GeoPoint(10.72798, 106.72018),
            new GeoPoint(10.80062, 106.71302),
            new GeoPoint(10.83834, 106.80718),
            new GeoPoint(10.76012, 106.65772));

    List<Driver> generate(int driverCount) {
        List<Driver> drivers = new ArrayList<>(driverCount);
        for (int index = 0; index < driverCount; index++) {
            drivers.add(new Driver("driver-" + index, STARTS.get(Math.floorMod(index, STARTS.size()))));
        }
        return List.copyOf(drivers);
    }
}
