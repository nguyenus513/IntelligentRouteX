package com.routechain.v2.perf;

import com.routechain.domain.GeoPoint;

import java.util.List;

final class RoadAwareMerchantSampler {
    private final List<GeoPoint> merchants = List.of(
            new GeoPoint(10.77633, 106.70066),
            new GeoPoint(10.77730, 106.70214),
            new GeoPoint(10.77810, 106.70417),
            new GeoPoint(10.77925, 106.70585),
            new GeoPoint(10.73126, 106.72163),
            new GeoPoint(10.72986, 106.72328),
            new GeoPoint(10.72864, 106.72470),
            new GeoPoint(10.72746, 106.72618),
            new GeoPoint(10.80278, 106.71453),
            new GeoPoint(10.80406, 106.71608),
            new GeoPoint(10.80518, 106.71782),
            new GeoPoint(10.80624, 106.71920),
            new GeoPoint(10.83986, 106.80888),
            new GeoPoint(10.84120, 106.81046),
            new GeoPoint(10.84248, 106.81210),
            new GeoPoint(10.84370, 106.81372),
            new GeoPoint(10.76128, 106.65908),
            new GeoPoint(10.76252, 106.66066),
            new GeoPoint(10.76382, 106.66222),
            new GeoPoint(10.76502, 106.66376));

    GeoPoint sample(int index) {
        return merchants.get(Math.floorMod(index, merchants.size()));
    }
}
