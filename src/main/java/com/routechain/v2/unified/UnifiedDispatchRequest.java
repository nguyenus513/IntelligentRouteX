package com.routechain.v2.unified;

import com.routechain.domain.Driver;
import com.routechain.domain.Order;
import com.routechain.domain.Region;
import com.routechain.domain.WeatherProfile;

import java.time.Instant;
import java.util.List;

public record UnifiedDispatchRequest(
        String schemaVersion,
        String traceId,
        DispatchMode mode,
        DispatchStrategy strategy,
        List<Order> orders,
        List<Driver> drivers,
        List<Region> regions,
        WeatherProfile weatherProfile,
        DispatchPolicy policy,
        Instant decisionTime) {

    public UnifiedDispatchRequest {
        schemaVersion = schemaVersion == null ? "unified-dispatch-request/v1" : schemaVersion;
        mode = mode == null ? DispatchMode.STATIC_FULL_COVERAGE : mode;
        strategy = strategy == null ? DispatchStrategy.MULTI_PASS_COVERAGE : strategy;
        orders = orders == null ? List.of() : List.copyOf(orders);
        drivers = drivers == null ? List.of() : List.copyOf(drivers);
        regions = regions == null ? List.of() : List.copyOf(regions);
        weatherProfile = weatherProfile == null ? WeatherProfile.CLEAR : weatherProfile;
        policy = policy == null ? DispatchPolicy.dashboardDefault(orders.size(), drivers.size()) : policy;
        decisionTime = decisionTime == null ? Instant.now() : decisionTime;
    }
}
