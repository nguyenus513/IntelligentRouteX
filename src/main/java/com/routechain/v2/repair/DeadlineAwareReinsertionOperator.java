package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class DeadlineAwareReinsertionOperator extends AbstractSuffixOperator implements SuffixRepairOperator {
    @Override
    public MutableSuffixState repair(MutableSuffixState state) {
        List<String> mutable = new ArrayList<>(state.mutableStops());
        mutable.remove(state.insertedOrderId());
        mutable.addFirst(state.insertedOrderId());
        List<String> removed = new ArrayList<>(state.removedStops());
        while (!removed.isEmpty()) {
            String orderId = removed.removeFirst();
            if (!mutable.contains(orderId)) {
                mutable.add(orderId);
            }
        }
        return state(state, mutable, removed, "alns-deadline-aware-reinsertion");
    }
}
