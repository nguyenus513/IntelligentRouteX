package com.routechain.v2.repair;

import java.util.ArrayList;
import java.util.List;

abstract class AbstractSuffixOperator {
    protected MutableSuffixState state(MutableSuffixState original,
                                       List<String> mutableStops,
                                       List<String> removedStops,
                                       String trace) {
        List<String> operatorTrace = new ArrayList<>(original.operatorTrace());
        operatorTrace.add(trace);
        boolean feasible = original.feasible()
                && !mutableStops.isEmpty()
                && mutableStops.contains(original.insertedOrderId())
                && mutableStops.size() == mutableStops.stream().distinct().count();
        List<String> violations = new ArrayList<>(original.violations());
        if (!mutableStops.contains(original.insertedOrderId())) {
            violations.add("mutable-suffix-missing-inserted-order");
        }
        if (mutableStops.size() != mutableStops.stream().distinct().count()) {
            violations.add("mutable-suffix-duplicate-order");
        }
        return new MutableSuffixState(
                original.routeId(),
                original.driverId(),
                original.frozenPrefixStops(),
                mutableStops,
                removedStops,
                original.insertedOrderId(),
                original.score(),
                feasible,
                violations.stream().distinct().toList(),
                operatorTrace.stream().distinct().toList());
    }
}
