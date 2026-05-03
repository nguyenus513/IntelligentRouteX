package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class OverloadedSuffixRemovalOperator extends AbstractSuffixOperator implements SuffixDestroyOperator {
    private static final int MAX_SUFFIX_SIZE = 3;

    @Override
    public MutableSuffixState destroy(MutableSuffixState state) {
        if (state.mutableStops().size() <= MAX_SUFFIX_SIZE) {
            return state(state, state.mutableStops(), state.removedStops(), "alns-overloaded-suffix-removal-skip");
        }
        List<String> mutable = new ArrayList<>(state.mutableStops());
        List<String> removedStops = new ArrayList<>(state.removedStops());
        while (mutable.size() > MAX_SUFFIX_SIZE) {
            String removed = mutable.removeLast();
            if (removed.equals(state.insertedOrderId())) {
                mutable.addFirst(removed);
                removed = mutable.removeLast();
            }
            removedStops.add(removed);
        }
        return state(state, mutable, removedStops, "alns-overloaded-suffix-removal");
    }
}
