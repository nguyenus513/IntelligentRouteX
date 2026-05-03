package com.routechain.v2.repair;

import java.util.List;

public record MutableSuffixState(
        String routeId,
        String driverId,
        List<String> frozenPrefixStops,
        List<String> mutableStops,
        List<String> removedStops,
        String insertedOrderId,
        double score,
        boolean feasible,
        List<String> violations,
        List<String> operatorTrace) {

    public MutableSuffixState {
        frozenPrefixStops = frozenPrefixStops == null ? List.of() : List.copyOf(frozenPrefixStops);
        mutableStops = mutableStops == null ? List.of() : List.copyOf(mutableStops);
        removedStops = removedStops == null ? List.of() : List.copyOf(removedStops);
        violations = violations == null ? List.of() : List.copyOf(violations);
        operatorTrace = operatorTrace == null ? List.of() : List.copyOf(operatorTrace);
    }
}
