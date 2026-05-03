package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class ShawRelatedRemovalOperator extends AbstractSuffixOperator implements SuffixDestroyOperator {
    @Override
    public MutableSuffixState destroy(MutableSuffixState state) {
        if (state.mutableStops().size() <= 2) {
            return state(state, state.mutableStops(), state.removedStops(), "alns-shaw-related-removal-skip");
        }
        List<String> mutable = new ArrayList<>(state.mutableStops());
        int insertedIndex = mutable.indexOf(state.insertedOrderId());
        int removeIndex = insertedIndex <= 0 ? 1 : insertedIndex - 1;
        String removed = mutable.remove(removeIndex);
        List<String> removedStops = new ArrayList<>(state.removedStops());
        removedStops.add(removed);
        return state(state, mutable, removedStops, "alns-shaw-related-removal");
    }
}
