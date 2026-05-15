package com.routechain.v2.quota;

import com.routechain.domain.Driver;
import com.routechain.v2.unified.DispatchPolicy;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class DriverQuotaBalancer {
    public Map<String, Integer> emptyLoads(List<Driver> drivers) {
        Map<String, Integer> loads = new LinkedHashMap<>();
        if (drivers != null) {
            drivers.forEach(driver -> loads.put(driver.driverId(), 0));
        }
        return loads;
    }

    public List<Driver> eligibleDrivers(List<Driver> drivers, Map<String, Integer> driverLoads, int maxOrdersPerDriver) {
        return drivers.stream()
                .filter(driver -> driverLoads.getOrDefault(driver.driverId(), 0) < maxOrdersPerDriver)
                .sorted(Comparator.comparingInt((Driver driver) -> driverLoads.getOrDefault(driver.driverId(), 0)).thenComparing(Driver::driverId))
                .toList();
    }

    public List<DriverLoadSummary> summarize(List<Driver> drivers, Map<String, Integer> driverLoads, DispatchPolicy policy, int orderCount) {
        int driverCount = Math.max(1, drivers.size());
        int min = policy.effectiveMinOrdersPerDriver(orderCount, driverCount);
        int target = policy.targetOrdersPerDriver(orderCount, driverCount);
        int max = policy.effectiveMaxOrdersPerDriver(orderCount, driverCount);
        return drivers.stream()
                .map(driver -> {
                    int load = driverLoads.getOrDefault(driver.driverId(), 0);
                    String status = load >= max ? "MAX" : load >= target ? "TARGET" : load >= min ? "MIN_SATISFIED" : "UNDER_MIN";
                    return new DriverLoadSummary(driver.driverId(), load, min, target, max, status);
                })
                .toList();
    }
}
