package com.routechain.v2.constraints;

import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public record ConstraintCheckResult(
        boolean feasible,
        List<ConstraintViolation> violations) {

    public ConstraintCheckResult {
        violations = violations == null ? List.of() : List.copyOf(violations);
    }

    public static ConstraintCheckResult ok() {
        return new ConstraintCheckResult(true, List.of());
    }

    public static ConstraintCheckResult infeasible(List<ConstraintViolation> violations) {
        return new ConstraintCheckResult(false, List.copyOf(violations));
    }

    public List<String> reasonCodes() {
        return violations.stream()
                .map(ConstraintViolation::code)
                .distinct()
                .toList();
    }

    public Map<String, Integer> violationCountsByCode() {
        Map<String, Integer> counts = new TreeMap<>();
        for (ConstraintViolation violation : violations) {
            counts.merge(violation.code(), 1, Integer::sum);
        }
        return Map.copyOf(counts);
    }
}
