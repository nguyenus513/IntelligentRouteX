package com.routechain.v2.hybrid;

import com.routechain.domain.Driver;
import com.routechain.domain.Order;

import java.util.List;
import java.util.Map;

public record SeedRouteBinding(
        String seedId,
        CandidateSource source,
        SolutionSeedCandidate seed,
        List<BoundRoute> routes,
        Map<String, Order> orderById,
        Map<String, Driver> driverById,
        boolean matrixBound,
        String matrixProvider) {

    public SeedRouteBinding {
        routes = routes == null ? List.of() : List.copyOf(routes);
        orderById = orderById == null ? Map.of() : Map.copyOf(orderById);
        driverById = driverById == null ? Map.of() : Map.copyOf(driverById);
        matrixProvider = matrixProvider == null ? "unknown" : matrixProvider;
    }
}
