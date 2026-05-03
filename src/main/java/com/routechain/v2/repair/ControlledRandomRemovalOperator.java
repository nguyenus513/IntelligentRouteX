package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

public final class ControlledRandomRemovalOperator extends AbstractSuffixOperator implements SuffixDestroyOperator {
    @Override
    public MutableSuffixState destroy(MutableSuffixState state) {
        if (state.mutableStops().size() <= 1) {
            return state(state, state.mutableStops(), state.removedStops(), "alns-controlled-random-removal-skip");
        }
        List<String> mutable = new ArrayList<>(state.mutableStops());
        int removeIndex = Math.floorMod(state.routeId().hashCode() + state.insertedOrderId().hashCode(), mutable.size());
        if (mutable.get(removeIndex).equals(state.insertedOrderId())) {
            removeIndex = (removeIndex + 1) % mutable.size();
        }
        String removed = mutable.remove(removeIndex);
        List<String> removedStops = new ArrayList<>(state.removedStops());
        removedStops.add(removed);
        return state(state, mutable, removedStops, "alns-controlled-random-removal");
    }
}
