package com.routechain.v2.selector;

public enum ConflictReason {
    ORDER_OVERLAP,
    DRIVER_OVERLAP,
    BUNDLE_OVERLAP,
    ACTIVE_ROUTE_MUTATION_OVERLAP,
    MANUAL_EXCLUSION
}
