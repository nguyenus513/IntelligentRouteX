package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class AlnsRepairEngine {
    private final RepairAcceptancePolicy acceptancePolicy = new RepairAcceptancePolicy();
    private final MutableSuffixAlns mutableSuffixAlns = new MutableSuffixAlns();
    private final List<RepairOperatorStrategy> repairOperators = List.of(
            new Regret2InsertionOperator(),
            new Regret3InsertionOperator(),
            new DeadlineAwareInsertionOperator(),
            new FreshnessAwareInsertionOperator(),
            new RestaurantAwareInsertionOperator(),
            new EjectionInsertionOperator(),
            new RouteSplitMergeOperator());

    public List<RepairCandidate> repair(RepairContext context) {
        return repairWithTelemetry(context).candidates();
    }

    public ActiveRouteRepairResult repairWithTelemetry(RepairContext context) {
        long startedAt = System.nanoTime();
        int maxIterations = Math.max(1, context.insertionCandidates().size() * (repairOperators.size() + 1));
        RepairBudgetController budget = new RepairBudgetController(context.runtimeBudget(), maxIterations);
        List<RepairCandidate> repaired = new ArrayList<>();
        RepairCandidate incumbent = null;
        double beforeBestScore = context.insertionCandidates().stream()
                .mapToDouble(ActiveRouteInsertionCandidate::score)
                .max()
                .orElse(0.0);
        Map<String, MutableOperatorStats> operatorStats = new LinkedHashMap<>();
        List<String> rejectionReasons = new ArrayList<>();
        boolean timedOut = false;
        int iteration = 0;
        for (ActiveRouteInsertionCandidate candidate : context.insertionCandidates().stream()
                .sorted(Comparator.comparingDouble(ActiveRouteInsertionCandidate::score).reversed())
                .toList()) {
            if (budget.canContinue(iteration++)) {
                RepairCandidate suffixCandidate = toRepairCandidate(mutableSuffixAlns.improve(candidate, budget.remainingBudget()));
                boolean accepted = acceptancePolicy.accept(incumbent, suffixCandidate, candidate.score());
                record(operatorStats, suffixCandidate, suffixCandidate.objectiveScore() - candidate.score(), accepted);
                if (accepted) {
                    incumbent = suffixCandidate;
                    repaired.add(suffixCandidate);
                } else {
                    rejectionReasons.add(rejectionReason(suffixCandidate, candidate.score(), incumbent));
                }
            } else {
                timedOut = true;
                break;
            }
            for (RepairOperatorStrategy repairOperator : repairOperators) {
                if (!budget.canContinue(iteration++)) {
                    timedOut = true;
                    return result(context, repaired, beforeBestScore, operatorStats, rejectionReasons, timedOut, startedAt);
                }
                RepairSolution solution = repairOperator.apply(candidate);
                RepairCandidate challenger = toRepairCandidate(solution);
                boolean accepted = acceptancePolicy.accept(incumbent, challenger, candidate.score());
                record(operatorStats, challenger, challenger.objectiveScore() - candidate.score(), accepted);
                if (accepted) {
                    incumbent = challenger;
                    repaired.add(challenger);
                } else {
                    rejectionReasons.add(rejectionReason(challenger, candidate.score(), incumbent));
                }
            }
        }
        return result(context, repaired, beforeBestScore, operatorStats, rejectionReasons, timedOut, startedAt);
    }

    private ActiveRouteRepairResult result(RepairContext context,
                                           List<RepairCandidate> repaired,
                                           double beforeBestScore,
                                           Map<String, MutableOperatorStats> operatorStats,
                                           List<String> rejectionReasons,
                                           boolean timedOut,
                                           long startedAt) {
        double afterBestScore = repaired.stream()
                .mapToDouble(RepairCandidate::objectiveScore)
                .max()
                .orElse(beforeBestScore);
        String bestCandidateId = repaired.stream()
                .max(Comparator.comparingDouble(RepairCandidate::objectiveScore))
                .map(candidate -> candidate.insertionCandidate().candidateId())
                .orElse("");
        double delta = Math.max(0.0, afterBestScore - beforeBestScore);
        int frozenPrefixViolationCount = countSignals(rejectionReasons, "frozen-prefix")
                + countSignals(repaired.stream().flatMap(candidate -> candidate.reasons().stream()).toList(), "frozen-prefix");
        int foodDurationViolationCount = countSignals(rejectionReasons, "food-duration")
                + countSignals(repaired.stream().flatMap(candidate -> candidate.reasons().stream()).toList(), "food-on-vehicle");
        double freshnessImprovementDelta = repaired.stream()
                .mapToDouble(candidate -> Math.max(0.0, 1.0 - candidate.insertionCandidate().freshnessRisk())
                        * Math.max(0.0, candidate.objectiveScore() - beforeBestScore))
                .max()
                .orElse(0.0);
        double tailRiskImprovementDelta = repaired.stream()
                .filter(candidate -> candidate.reasons().stream().anyMatch(reason -> reason.contains("late") || reason.contains("urgent") || reason.contains("deadline")))
                .mapToDouble(candidate -> Math.max(0.0, candidate.objectiveScore() - beforeBestScore))
                .max()
                .orElse(0.0);
        List<RepairOperatorStat> stats = operatorStats.values().stream()
                .map(MutableOperatorStats::toStat)
                .toList();
        int acceptedMoves = stats.stream().mapToInt(RepairOperatorStat::acceptedCount).sum();
        int rejectedMoves = stats.stream().mapToInt(RepairOperatorStat::rejectedCount).sum();
        List<String> degradeReasons = new ArrayList<>();
        if (timedOut) {
            degradeReasons.add("active-repair-timeout-best-incumbent");
        }
        if (repaired.isEmpty()) {
            degradeReasons.add("active-repair-no-improvement");
        } else {
            degradeReasons.add("active-route-bounded-alns-repair-applied");
        }
        RepairTelemetry telemetry = new RepairTelemetry(
                "repair-telemetry/v1",
                context.insertionCandidates().size(),
                repaired.size(),
                stats.stream().mapToInt(RepairOperatorStat::triedCount).sum(),
                acceptedMoves,
                rejectedMoves,
                timedOut,
                Math.max(0L, (System.nanoTime() - startedAt) / 1_000_000L),
                delta,
                stats,
                rejectionReasons.stream().distinct().toList(),
                degradeReasons,
                new RepairImprovementSummary(
                        beforeBestScore,
                        afterBestScore,
                        delta,
                        bestCandidateId,
                        frozenPrefixViolationCount,
                        foodDurationViolationCount,
                        freshnessImprovementDelta,
                        tailRiskImprovementDelta));
        return new ActiveRouteRepairResult(repaired, telemetry, degradeReasons);
    }

    private int countSignals(List<String> reasons, String signal) {
        return (int) reasons.stream()
                .filter(reason -> reason != null && reason.contains(signal))
                .count();
    }

    private void record(Map<String, MutableOperatorStats> operatorStats,
                        RepairCandidate candidate,
                        double delta,
                        boolean accepted) {
        for (String operatorName : candidate.operatorsApplied()) {
            operatorStats.computeIfAbsent(operatorName, MutableOperatorStats::new).record(delta, accepted);
        }
    }

    private String rejectionReason(RepairCandidate challenger, double baselineScore, RepairCandidate incumbent) {
        if (challenger == null || !challenger.feasible()) {
            return "repair-reject-hard-infeasible";
        }
        if (challenger.reasons().stream().anyMatch(reason -> reason.contains("frozen-prefix"))) {
            return "repair-reject-frozen-prefix-mutated";
        }
        if (challenger.insertionCandidate().freshnessRisk() > 0.85) {
            return "repair-reject-food-duration";
        }
        if (challenger.insertionCandidate().churnRisk() > 0.75) {
            return "repair-reject-route-churn";
        }
        if (challenger.objectiveScore() <= baselineScore + 1e-9) {
            return "repair-reject-no-improvement";
        }
        if (incumbent != null && challenger.objectiveScore() <= incumbent.objectiveScore() + 1e-9) {
            return "repair-reject-objective-below-incumbent";
        }
        return "active-repair-no-improvement";
    }

    private RepairCandidate toRepairCandidate(RepairSolution solution) {
        List<String> reasons = new ArrayList<>(solution.reasons());
        reasons.add("bounded-alns-repair-candidate");
        return new RepairCandidate(
                new ActiveRouteInsertionCandidate(
                        solution.candidate().schemaVersion(),
                        solution.candidate().candidateId(),
                        solution.candidate().routeId(),
                        solution.candidate().driverId(),
                        solution.candidate().insertedOrderId(),
                        solution.candidate().pickupInsertionIndex(),
                        solution.candidate().newStopOrder(),
                        solution.candidate().projectedPickupEtaMinutes(),
                        solution.candidate().projectedCompletionEtaMinutes(),
                        solution.candidate().incrementalCompletionEtaMinutes(),
                        solution.candidate().freshnessRisk(),
                        solution.candidate().churnRisk(),
                        solution.candidate().routeShapeRisk(),
                        solution.score(),
                        solution.feasible(),
                        reasons.stream().distinct().toList(),
                        solution.candidate().degradeReasons()),
                solution.score(),
                solution.feasible(),
                solution.operatorNames(),
                reasons.stream().distinct().toList());
    }

    private static final class MutableOperatorStats {
        private final String operatorName;
        private int tried;
        private int accepted;
        private double totalDelta;
        private double bestDelta = Double.NEGATIVE_INFINITY;

        private MutableOperatorStats(String operatorName) {
            this.operatorName = operatorName;
        }

        private void record(double delta, boolean acceptedMove) {
            tried++;
            if (acceptedMove) {
                accepted++;
            }
            totalDelta += delta;
            bestDelta = Math.max(bestDelta, delta);
        }

        private RepairOperatorStat toStat() {
            return new RepairOperatorStat(
                    operatorName,
                    tried,
                    accepted,
                    tried - accepted,
                    bestDelta == Double.NEGATIVE_INFINITY ? 0.0 : bestDelta,
                    tried == 0 ? 0.0 : totalDelta / tried);
        }
    }
}
