package com.routechain.v2.coverage;

import com.routechain.domain.Order;
import com.routechain.v2.executor.DispatchAssignment;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class CoverageValidator {
    public CoverageSummary validate(List<Order> inputOrders, List<DispatchAssignment> assignments, int deferredCount, int rejectedCount, boolean staticFinal) {
        Set<String> seen = new HashSet<>();
        int duplicate = 0;
        for (DispatchAssignment assignment : assignments == null ? List.<DispatchAssignment>of() : assignments) {
            for (String orderId : assignment.orderIds()) {
                if (!seen.add(orderId)) {
                    duplicate++;
                }
            }
        }
        int input = inputOrders == null ? 0 : inputOrders.size();
        int assigned = seen.size();
        int uncovered = Math.max(0, input - assigned - deferredCount - rejectedCount);
        int accounted = assigned + deferredCount + rejectedCount + uncovered;
        boolean invariant = accounted == input && duplicate == 0 && (!staticFinal || deferredCount == 0);
        double rate = input == 0 ? 1.0 : (assigned + deferredCount + rejectedCount) / (double) input;
        return new CoverageSummary(input, assigned, deferredCount, rejectedCount, uncovered, duplicate, accounted, invariant, rate, staticFinal && deferredCount > 0);
    }
}
