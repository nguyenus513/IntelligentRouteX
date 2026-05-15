package com.routechain.v2.unified;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.Region;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2CompatibleCore;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UnifiedDispatchCoreCoverageTest {
    @Test
    void staticDemoMAssignsAllOrdersAndBalancesFourDrivers() {
        UnifiedDispatchCore core = disabledFallbackUnifiedCore();
        UnifiedDispatchResult result = core.dispatch(request(20, 4));

        assertEquals(20, result.coverageSummary().inputOrderCount());
        assertEquals(20, result.coverageSummary().assignedOrderCount());
        assertEquals(0, result.coverageSummary().deferredOrderCount());
        assertEquals(0, result.coverageSummary().duplicateAssignedOrderCount());
        assertTrue(result.coverageSummary().accountingInvariantPassed());
        assertEquals(4, result.dispatchResult().assignments().size());
        assertTrue(result.driverLoadSummary().stream().allMatch(load -> load.assignedOrderCount() >= 4));
        assertTrue(result.driverLoadSummary().stream().allMatch(load -> load.assignedOrderCount() <= load.maxOrderCount()));
    }

    @Test
    void dynamicMaxExpandsWhenOrderCountExceedsConfiguredMax() {
        DispatchPolicy policy = DispatchPolicy.dashboardDefault(30, 4);

        assertEquals(8, policy.targetOrdersPerDriver(30, 4));
        assertTrue(policy.effectiveMaxOrdersPerDriver(30, 4) >= 9);
    }

    @Test
    void effectiveMinDoesNotExceedPossibleLoad() {
        DispatchPolicy policy = DispatchPolicy.dashboardDefault(10, 4);

        assertEquals(2, policy.effectiveMinOrdersPerDriver(10, 4));
    }

    @Test
    void dashboardRepairIsNotUsedForUnifiedCoverage() {
        UnifiedDispatchResult result = disabledFallbackUnifiedCore().dispatch(request(12, 3));

        assertEquals("DRAIN_UNTIL_ACCOUNTED", result.diagnostics().get("coverageMode"));
        assertFalse(result.dispatchResult().degradeReasons().contains("dashboard-balanced-coverage-repair"));
        assertTrue(result.dispatchResult().degradeReasons().contains("dashboard-repair-disabled-core-owned-coverage"));
    }

    private static UnifiedDispatchCore disabledFallbackUnifiedCore() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setEnabled(false);
        return new UnifiedDispatchCore(new DispatchV2CompatibleCore(properties, null));
    }

    private static UnifiedDispatchRequest request(int orderCount, int driverCount) {
        List<Order> orders = java.util.stream.IntStream.range(0, orderCount)
                .mapToObj(index -> new Order(
                        "ORD-" + String.format("%03d", index + 1),
                        point(index * 17 + 3),
                        point(index * 29 + 11),
                        Instant.now(),
                        Instant.now(),
                        60,
                        false))
                .toList();
        List<Driver> drivers = java.util.stream.IntStream.range(0, driverCount)
                .mapToObj(index -> new Driver("D" + String.format("%02d", index + 1), point(index * 41 + 19)))
                .toList();
        return new UnifiedDispatchRequest(
                "unified-dispatch-request/v1",
                "TEST-" + orderCount + "-" + driverCount,
                DispatchMode.STATIC_FULL_COVERAGE,
                DispatchStrategy.MULTI_PASS_COVERAGE,
                orders,
                drivers,
                List.of(new Region("hcm", "Ho Chi Minh City")),
                WeatherProfile.CLEAR,
                DispatchPolicy.dashboardDefault(orderCount, driverCount),
                Instant.now());
    }

    private static GeoPoint point(int seed) {
        double x = Math.abs(Math.sin(seed * 12.9898) * 43758.5453) % 1.0;
        double y = Math.abs(Math.sin(seed * 78.233) * 19341.1327) % 1.0;
        return new GeoPoint(10.755 + (10.805 - 10.755) * x, 106.670 + (106.725 - 106.670) * y);
    }
}
