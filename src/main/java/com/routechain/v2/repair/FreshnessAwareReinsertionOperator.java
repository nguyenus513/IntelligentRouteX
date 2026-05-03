package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class FreshnessAwareReinsertionOperator extends AbstractSuffixOperator implements SuffixRepairOperator {
    @Override
    public MutableSuffixState repair(MutableSuffixState state) {
        List<String> mutable = new ArrayList<>(state.mutableStops());
        List<String> removed = new ArrayList<>(state.removedStops());
        while (!removed.isEmpty()) {
            String orderId = removed.removeLast();
            if (!mutable.contains(orderId)) {
                mutable.add(Math.min(1, mutable.size()), orderId);
            }
        }
        return state(state, mutable, removed, "alns-freshness-aware-reinsertion");
    }
}
