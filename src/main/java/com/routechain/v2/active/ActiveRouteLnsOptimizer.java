package com.routechain.v2.active;

import java.util.Comparator;
import java.util.List;

public final class ActiveRouteLnsOptimizer {
    private static final int MAX_RETAINED_CANDIDATES = 16;

    public ActiveRouteLnsRepairResult improve(List<ActiveRouteInsertionCandidate> candidates) {
        if (candidates == null || candidates.isEmpty()) {
            return new ActiveRouteLnsRepairResult(
                    "active-route-lns-repair-result/v1",
                    List.of(),
                    0,
                    0,
                    List.of(),
                    List.of("active-lns-no-candidates"));
        }
        List<ActiveRouteInsertionCandidate> retained = candidates.stream()
                .filter(ActiveRouteInsertionCandidate::feasible)
                .sorted(Comparator.comparingDouble(this::lnsObjective).reversed()
                        .thenComparingDouble(ActiveRouteInsertionCandidate::projectedCompletionEtaMinutes)
                        .thenComparing(ActiveRouteInsertionCandidate::candidateId))
                .limit(MAX_RETAINED_CANDIDATES)
                .map(this::tagLnsCandidate)
                .toList();
        return new ActiveRouteLnsRepairResult(
                "active-route-lns-repair-result/v1",
                retained,
                candidates.size(),
                retained.size(),
                List.of("bounded-regret-retain", "freshness-aware-filter", "route-shape-aware-rank"),
                retained.isEmpty() ? List.of("active-lns-no-feasible-candidates") : List.of());
    }

    private double lnsObjective(ActiveRouteInsertionCandidate candidate) {
        return candidate.score()
                - 0.18 * candidate.freshnessRisk()
                - 0.16 * candidate.churnRisk()
                - 0.12 * candidate.routeShapeRisk()
                - 0.08 * Math.max(0.0, candidate.incrementalCompletionEtaMinutes() / 12.0);
    }

    private ActiveRouteInsertionCandidate tagLnsCandidate(ActiveRouteInsertionCandidate candidate) {
        java.util.ArrayList<String> reasons = new java.util.ArrayList<>(candidate.reasons());
        reasons.add("active-lns-bounded-repair-retained");
        return new ActiveRouteInsertionCandidate(
                candidate.schemaVersion(),
                candidate.candidateId(),
                candidate.routeId(),
                candidate.driverId(),
                candidate.insertedOrderId(),
                candidate.pickupInsertionIndex(),
                candidate.newStopOrder(),
                candidate.projectedPickupEtaMinutes(),
                candidate.projectedCompletionEtaMinutes(),
                candidate.incrementalCompletionEtaMinutes(),
                candidate.freshnessRisk(),
                candidate.churnRisk(),
                candidate.routeShapeRisk(),
                Math.max(0.0, Math.min(1.0, candidate.score() + 0.02)),
                candidate.feasible(),
                reasons.stream().distinct().toList(),
                candidate.degradeReasons());
    }
}
