package com.routechain.v2.seedimprovement;

import java.util.ArrayList;
import java.util.List;

public final class HeuristicPdLnsImprover {
    private final PdOrderImpactAnalyzer impactAnalyzer;
    private final PdExactInsertionOperator exactInsertion;
    private final PdSeedEvaluator evaluator;
    private final PdObjectiveComparator comparator;

    public HeuristicPdLnsImprover() {
        this(new PdOrderImpactAnalyzer(), new PdExactInsertionOperator(), new PdSeedEvaluator(), new PdObjectiveComparator());
    }

    public HeuristicPdLnsImprover(PdOrderImpactAnalyzer impactAnalyzer,
                                  PdExactInsertionOperator exactInsertion,
                                  PdSeedEvaluator evaluator,
                                  PdObjectiveComparator comparator) {
        this.impactAnalyzer = impactAnalyzer == null ? new PdOrderImpactAnalyzer() : impactAnalyzer;
        this.exactInsertion = exactInsertion == null ? new PdExactInsertionOperator() : exactInsertion;
        this.evaluator = evaluator == null ? new PdSeedEvaluator() : evaluator;
        this.comparator = comparator == null ? new PdObjectiveComparator() : comparator;
    }

    public PdLnsResult improve(PdSeedState baseSeed, int maxRounds, int ordersPerRound) {
        PdEvaluation baseEvaluation = evaluator.evaluateSeed(baseSeed);
        if (baseSeed == null || !baseEvaluation.valid()) {
            return new PdLnsResult(false, baseSeed, baseSeed, baseEvaluation, baseEvaluation, 0, 0, 0, 0, 0, List.of());
        }
        PdSeedState current = baseSeed;
        PdEvaluation currentEvaluation = baseEvaluation;
        PdSeedState best = baseSeed;
        PdEvaluation bestEvaluation = baseEvaluation;
        List<PdLnsTrace> traces = new ArrayList<>();
        int evaluatedOrders = 0;
        int evaluatedInsertions = 0;
        int feasibleInsertions = 0;
        int acceptedMutations = 0;
        int safeRounds = Math.max(1, maxRounds);
        int safeOrdersPerRound = Math.max(1, ordersPerRound);
        for (int round = 1; round <= safeRounds; round++) {
            List<PdOrderImpact> badOrders = impactAnalyzer.rankBadOrders(current).stream()
                    .limit(safeOrdersPerRound)
                    .toList();
            if (badOrders.isEmpty()) {
                break;
            }
            for (PdOrderImpact impact : badOrders) {
                evaluatedOrders++;
                PdInsertionCandidate insertion = exactInsertion.bestInsert(current, impact.orderId());
                evaluatedInsertions += insertion.evaluatedCandidates();
                feasibleInsertions += insertion.feasibleCandidates();
                PdEvaluation candidateEvaluation = insertion.evaluation();
                boolean accepted = candidateEvaluation != null
                        && comparator.validNoRegression(candidateEvaluation, currentEvaluation)
                        && comparator.better(candidateEvaluation, bestEvaluation);
                if (accepted) {
                    double oldKm = currentEvaluation.distanceKm();
                    current = insertion.seed();
                    currentEvaluation = candidateEvaluation;
                    best = current;
                    bestEvaluation = currentEvaluation;
                    acceptedMutations++;
                    traces.add(new PdLnsTrace(round, impact.orderId(), "PD_EXACT_INSERTION", true, oldKm, candidateEvaluation.distanceKm(), round(oldKm - candidateEvaluation.distanceKm()), insertion.evaluatedCandidates(), insertion.feasibleCandidates(), ""));
                } else {
                    String reason = candidateEvaluation == null ? "no-feasible-insertion" : candidateEvaluation.rejectReason().isBlank() ? "no-objective-improvement" : candidateEvaluation.rejectReason();
                    traces.add(new PdLnsTrace(round, impact.orderId(), "PD_EXACT_INSERTION", false, currentEvaluation.distanceKm(), candidateEvaluation == null ? currentEvaluation.distanceKm() : candidateEvaluation.distanceKm(), 0.0, insertion.evaluatedCandidates(), insertion.feasibleCandidates(), reason));
                }
            }
        }
        boolean applied = evaluatedOrders > 0 && evaluatedInsertions > 0;
        return new PdLnsResult(applied, baseSeed, best, baseEvaluation, bestEvaluation, safeRounds, evaluatedOrders, evaluatedInsertions, feasibleInsertions, acceptedMutations, traces);
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
