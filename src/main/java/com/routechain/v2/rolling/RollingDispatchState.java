package com.routechain.v2.rolling;

import com.routechain.domain.Driver;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.SchemaVersioned;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;

public record RollingDispatchState(
        String schemaVersion,
        String traceId,
        Instant decisionTime,
        List<Order> pendingOrders,
        List<Driver> availableDrivers,
        WeatherProfile weatherProfile,
        List<RollingOrderState> orderStates) implements SchemaVersioned {

    public RollingDispatchState {
        pendingOrders = pendingOrders == null ? List.of() : List.copyOf(pendingOrders);
        availableDrivers = availableDrivers == null ? List.of() : List.copyOf(availableDrivers);
        orderStates = orderStates == null ? List.of() : List.copyOf(orderStates);
    }

    public static RollingDispatchState fromRequest(DispatchV2Request request) {
        Instant decisionTime = request.decisionTime() == null ? Instant.now() : request.decisionTime();
        return new RollingDispatchState(
                "rolling-dispatch-state/v1",
                request.traceId(),
                decisionTime,
                request.openOrders().stream().sorted(Comparator.comparing(Order::orderId)).toList(),
                request.availableDrivers().stream().sorted(Comparator.comparing(Driver::driverId)).toList(),
                request.weatherProfile(),
                List.of());
    }
}
