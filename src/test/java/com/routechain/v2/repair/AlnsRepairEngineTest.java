package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AlnsRepairEngineTest {
    private final AlnsRepairEngine engine = new AlnsRepairEngine();

    @Test
    void appliesBoundedRepairOperatorsToFeasibleCandidate() {
        ActiveRouteRepairResult result = engine.repairWithTelemetry(new RepairContext(
                List.of(),
                List.of(candidate("c1", true, 0.70, 0.10, 0.10, 0.10, 4.0)),
                Duration.ofMillis(100)));
        List<RepairCandidate> repaired = result.candidates();

        assertFalse(repaired.isEmpty());
        assertTrue(result.telemetry().operatorsTried() > 0);
        assertTrue(result.telemetry().acceptedMoves() > 0);
        assertTrue(result.telemetry().bestImprovementDelta() > 0.0);
        assertTrue(repaired.get(0).reasons().contains("bounded-alns-repair-candidate"));
        assertTrue(repaired.stream().flatMap(candidate -> candidate.operatorsApplied().stream()).anyMatch(operator -> operator.contains("REGRET") || operator.contains("reinsertion")));
        assertTrue(repaired.getLast().objectiveScore() > 0.70);
    }

    @Test
    void rejectsInfeasibleRepairCandidates() {
        ActiveRouteRepairResult result = engine.repairWithTelemetry(new RepairContext(
                List.of(),
                List.of(candidate("bad", false, 0.95, 0.10, 0.10, 0.10, 4.0)),
                Duration.ofMillis(100)));

        assertTrue(result.candidates().isEmpty());
        assertTrue(result.telemetry().rejectedMoves() > 0);
        assertTrue(result.telemetry().degradeReasons().contains("active-repair-no-improvement"));
    }

    @Test
    void freshnessOperatorCanImproveLowRiskCandidate() {
        List<RepairCandidate> repaired = engine.repair(new RepairContext(
                List.of(),
                List.of(candidate("fresh", true, 0.55, 0.05, 0.20, 0.10, 6.0)),
                Duration.ofMillis(100)));

        assertTrue(repaired.stream().anyMatch(candidate -> candidate.reasons().contains("alns-freshness-aware-insertion")));
    }

    @Test
    void recordsMutableSuffixDestroyRepairTrace() {
        List<RepairCandidate> repaired = engine.repair(new RepairContext(
                List.of(),
                List.of(candidate("suffix", true, 0.60, 0.10, 0.10, 0.10, 4.0)),
                Duration.ofMillis(100)));

        assertTrue(repaired.stream().anyMatch(candidate -> candidate.reasons().stream().anyMatch(reason -> reason.contains("removal"))));
        assertTrue(repaired.stream().anyMatch(candidate -> candidate.reasons().stream().anyMatch(reason -> reason.contains("reinsertion"))));
    }

    @Test
    void deadlineOperatorRescuesLateRiskOrderAndRecordsTailImprovement() {
        ActiveRouteRepairResult result = engine.repairWithTelemetry(new RepairContext(
                List.of(),
                List.of(candidate("late", true, 0.50, 0.10, 0.10, 0.10, 5.0, List.of("late-risk-order"), List.of())),
                Duration.ofMillis(100)));

        assertTrue(result.candidates().stream().anyMatch(candidate -> candidate.reasons().contains("alns-deadline-aware-insertion")));
        assertTrue(result.telemetry().improvementSummary().tailRiskImprovementDelta() > 0.0);
    }

    @Test
    void freshnessAwareRepairRejectsUnsafeFoodDurationRisk() {
        ActiveRouteRepairResult result = engine.repairWithTelemetry(new RepairContext(
                List.of(),
                List.of(candidate("hot-food", true, 0.80, 0.90, 0.10, 0.10, 4.0)),
                Duration.ofMillis(100)));

        assertTrue(result.candidates().stream().noneMatch(candidate -> candidate.insertionCandidate().freshnessRisk() > 0.85));
        assertTrue(result.telemetry().rejectionReasons().contains("repair-reject-food-duration"));
        assertTrue(result.telemetry().improvementSummary().foodDurationViolationCount() > 0);
    }

    @Test
    void ejectionAndSplitMergeOperatorsImproveOverloadedSuffix() {
        ActiveRouteRepairResult result = engine.repairWithTelemetry(new RepairContext(
                List.of(),
                List.of(candidate("overload", true, 0.45, 0.50, 0.10, 0.80, 7.0,
                        List.of("active-route-regret-insertion"), List.of(), List.of("o0", "o1", "o2", "o3", "o4", "o5"))),
                Duration.ofMillis(100)));

        assertTrue(result.candidates().stream().flatMap(candidate -> candidate.operatorsApplied().stream())
                .anyMatch(operator -> operator.equals(RepairOperator.EJECTION_INSERTION.name())
                        || operator.equals(RepairOperator.ROUTE_SPLIT_MERGE.name())));
        assertTrue(result.telemetry().bestImprovementDelta() > 0.0);
    }

    @Test
    void rejectsFrozenPrefixMutationSignal() {
        ActiveRouteRepairResult result = engine.repairWithTelemetry(new RepairContext(
                List.of(),
                List.of(candidate("frozen", true, 0.80, 0.10, 0.10, 0.10, 4.0, List.of("frozen-prefix-violation"), List.of())),
                Duration.ofMillis(100)));

        assertTrue(result.candidates().isEmpty());
        assertTrue(result.telemetry().rejectionReasons().contains("repair-reject-frozen-prefix-mutated"));
        assertTrue(result.telemetry().improvementSummary().frozenPrefixViolationCount() > 0);
    }

    @Test
    void tinyBudgetReturnsBestIncumbentAndTelemetryTimeout() {
        List<ActiveRouteInsertionCandidate> candidates = java.util.stream.IntStream.range(0, 40)
                .mapToObj(index -> candidate("budget-" + index, true, 0.40 + index * 0.001, 0.10, 0.10, 0.10, 4.0))
                .toList();

        ActiveRouteRepairResult result = engine.repairWithTelemetry(new RepairContext(
                List.of(),
                candidates,
                Duration.ofNanos(1)));

        assertTrue(result.telemetry().timedOut());
        assertTrue(result.degradeReasons().contains("active-repair-timeout-best-incumbent"));
        assertTrue(result.telemetry().runtimeMs() < 500);
    }

    private ActiveRouteInsertionCandidate candidate(String id,
                                                    boolean feasible,
                                                    double score,
                                                    double freshnessRisk,
                                                    double churnRisk,
                                                    double shapeRisk,
                                                    double incrementalCompletionEtaMinutes) {
        return new ActiveRouteInsertionCandidate(
                "active-route-insertion-candidate/v1",
                id,
                "route-1",
                "driver-1",
                "order-1",
                1,
                List.of("order-0", "order-1"),
                3.0,
                12.0,
                incrementalCompletionEtaMinutes,
                freshnessRisk,
                churnRisk,
                shapeRisk,
                score,
                feasible,
                List.of("active-route-regret-insertion"),
                feasible ? List.of() : List.of("active-insertion-precedence-violation"));
    }

    private ActiveRouteInsertionCandidate candidate(String id,
                                                    boolean feasible,
                                                    double score,
                                                    double freshnessRisk,
                                                    double churnRisk,
                                                    double shapeRisk,
                                                    double incrementalCompletionEtaMinutes,
                                                    List<String> reasons,
                                                    List<String> degradeReasons) {
        return candidate(id, feasible, score, freshnessRisk, churnRisk, shapeRisk, incrementalCompletionEtaMinutes, reasons, degradeReasons, List.of("order-0", "order-1"));
    }

    private ActiveRouteInsertionCandidate candidate(String id,
                                                    boolean feasible,
                                                    double score,
                                                    double freshnessRisk,
                                                    double churnRisk,
                                                    double shapeRisk,
                                                    double incrementalCompletionEtaMinutes,
                                                    List<String> reasons,
                                                    List<String> degradeReasons,
                                                    List<String> stopOrder) {
        return new ActiveRouteInsertionCandidate(
                "active-route-insertion-candidate/v1",
                id,
                "route-1",
                "driver-1",
                "order-1",
                1,
                stopOrder,
                3.0,
                12.0,
                incrementalCompletionEtaMinutes,
                freshnessRisk,
                churnRisk,
                shapeRisk,
                score,
                feasible,
                reasons,
                degradeReasons);
    }
}
