package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class RegretOrderReinsertionOperator extends AbstractSuffixOperator implements SuffixRepairOperator {
    @Override
    public MutableSuffixState repair(MutableSuffixState state) {
        List<String> mutable = new ArrayList<>(state.mutableStops());
        List<String> removed = new ArrayList<>(state.removedStops());
        while (!removed.isEmpty()) {
            String orderId = removed.removeFirst();
            if (!mutable.contains(orderId)) {
                mutable.add(Math.min(mutable.size(), Math.max(1, mutable.indexOf(state.insertedOrderId()) + 1)), orderId);
            }
        }
        return state(state, mutable, removed, "alns-regret-order-reinsertion");
    }
}
