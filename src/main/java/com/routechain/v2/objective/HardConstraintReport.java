package com.routechain.v2.objective;

import java.util.List;

public record HardConstraintReport(
        boolean feasible,
        List<String> violations) {

    public static HardConstraintReport ok() {
        return new HardConstraintReport(true, List.of());
    }

    public static HardConstraintReport infeasible(List<String> violations) {
        return new HardConstraintReport(false, List.copyOf(violations));
    }
}
