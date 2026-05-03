package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class HighDetourRemovalOperator extends AbstractSuffixOperator implements SuffixDestroyOperator {
    @Override
    public MutableSuffixState destroy(MutableSuffixState state) {
        if (state.mutableStops().size() <= 2) {
            return state(state, state.mutableStops(), state.removedStops(), "alns-high-detour-removal-skip");
        }
        int removeIndex = Math.max(0, state.mutableStops().size() / 2);
        if (state.mutableStops().get(removeIndex).equals(state.insertedOrderId())) {
            removeIndex = Math.min(state.mutableStops().size() - 1, removeIndex + 1);
        }
        List<String> mutable = new ArrayList<>(state.mutableStops());
        String removed = mutable.remove(removeIndex);
        List<String> removedStops = new ArrayList<>(state.removedStops());
        removedStops.add(removed);
        return state(state, mutable, removedStops, "alns-high-detour-removal");
    }
}
