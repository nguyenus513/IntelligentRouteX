package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class LateRiskRemovalOperator extends AbstractSuffixOperator implements SuffixDestroyOperator {
    @Override
    public MutableSuffixState destroy(MutableSuffixState state) {
        if (state.mutableStops().size() <= 1) {
            return state(state, state.mutableStops(), state.removedStops(), "alns-late-risk-removal-skip");
        }
        List<String> mutable = new ArrayList<>(state.mutableStops());
        String removed = mutable.removeLast();
        if (removed.equals(state.insertedOrderId()) && !mutable.isEmpty()) {
            mutable.add(removed);
            removed = mutable.remove(Math.max(0, mutable.size() - 2));
        }
        List<String> removedStops = new ArrayList<>(state.removedStops());
        removedStops.add(removed);
        return state(state, mutable, removedStops, "alns-late-risk-removal");
    }
}
