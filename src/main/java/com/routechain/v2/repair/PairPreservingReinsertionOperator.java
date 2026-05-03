package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

public final class PairPreservingReinsertionOperator extends AbstractSuffixOperator implements SuffixRepairOperator {
    @Override
    public MutableSuffixState repair(MutableSuffixState state) {
        LinkedHashSet<String> ordered = new LinkedHashSet<>(state.mutableStops());
        ordered.addAll(state.removedStops());
        if (!ordered.contains(state.insertedOrderId())) {
            ordered.add(state.insertedOrderId());
        }
        return state(state, new ArrayList<>(ordered), List.of(), "alns-pair-preserving-reinsertion");
    }
}
