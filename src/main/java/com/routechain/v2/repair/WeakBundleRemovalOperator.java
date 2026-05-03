package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class WeakBundleRemovalOperator extends AbstractSuffixOperator implements SuffixDestroyOperator {
    @Override
    public MutableSuffixState destroy(MutableSuffixState state) {
        List<String> mutable = new ArrayList<>(state.mutableStops());
        String removed = mutable.stream()
                .filter(orderId -> !orderId.equals(state.insertedOrderId()))
                .findFirst()
                .orElse(null);
        if (removed == null) {
            return state(state, state.mutableStops(), state.removedStops(), "alns-weak-bundle-removal-skip");
        }
        mutable.remove(removed);
        List<String> removedStops = new ArrayList<>(state.removedStops());
        removedStops.add(removed);
        return state(state, mutable, removedStops, "alns-weak-bundle-removal");
    }
}
