package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class RouteShapeAwareReinsertionOperator extends AbstractSuffixOperator implements SuffixRepairOperator {
    @Override
    public MutableSuffixState repair(MutableSuffixState state) {
        List<String> mutable = new ArrayList<>(state.mutableStops());
        List<String> removed = new ArrayList<>(state.removedStops());
        removed.sort(Comparator.naturalOrder());
        for (String orderId : removed) {
            if (!mutable.contains(orderId)) {
                mutable.add(orderId);
            }
        }
        return state(state, mutable, List.of(), "alns-route-shape-aware-reinsertion");
    }
}
