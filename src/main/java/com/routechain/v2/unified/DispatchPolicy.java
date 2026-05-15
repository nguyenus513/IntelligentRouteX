package com.routechain.v2.unified;

public record DispatchPolicy(
        CoreCoverageMode coverageMode,
        int maxPasses,
        int minOrdersPerDriver,
        int maxOrdersPerDriver,
        boolean dynamicMaxEnabled,
        int overflowBuffer,
        boolean balancedRepairEnabled,
        boolean singletonFallbackEnabled) {

    public static DispatchPolicy dashboardDefault(int orderCount, int driverCount) {
        int eligibleDrivers = Math.max(1, driverCount);
        int target = (int) Math.ceil(orderCount / (double) eligibleDrivers);
        int configuredMax = 6;
        return new DispatchPolicy(
                CoreCoverageMode.DRAIN_UNTIL_ACCOUNTED,
                orderCount > 20 ? 2 : 1,
                4,
                Math.max(configuredMax, target + 1),
                true,
                1,
                true,
                true);
    }

    public int effectiveMinOrdersPerDriver(int orderCount, int eligibleDriverCount) {
        return Math.min(Math.max(0, minOrdersPerDriver), Math.max(0, orderCount / Math.max(1, eligibleDriverCount)));
    }

    public int targetOrdersPerDriver(int orderCount, int eligibleDriverCount) {
        return (int) Math.ceil(orderCount / (double) Math.max(1, eligibleDriverCount));
    }

    public int effectiveMaxOrdersPerDriver(int orderCount, int eligibleDriverCount) {
        if (!dynamicMaxEnabled) {
            return Math.max(1, maxOrdersPerDriver);
        }
        return Math.max(Math.max(1, maxOrdersPerDriver), targetOrdersPerDriver(orderCount, eligibleDriverCount) + Math.max(0, overflowBuffer));
    }
}
