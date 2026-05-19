package com.routechain.v2.seedimprovement;

import com.routechain.v2.mlproof.MlParticipationRecorder;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class PdDestroyRepairOperator {
    private final MlPdDestroyPolicy destroyPolicy;
    private final PdExactInsertionOperator exactInsertion;
    private final RegretKPickupDeliveryRepair repair;
    private final PdCrossInsertionOperator crossInsertion;
    private final PdSwapStarOperator swapStar;
    private final TabularMutationScorer tabularScorer;
    private final PdSeedEvaluator evaluator;
    private final PdObjectiveComparator comparator;

    public PdDestroyRepairOperator() {
        this(new MlPdDestroyPolicy(), new PdExactInsertionOperator(), new RegretKPickupDeliveryRepair(), new PdCrossInsertionOperator(), new PdSwapStarOperator(), new TabularMutationScorer(), new PdSeedEvaluator(), new PdObjectiveComparator());
    }

    public PdDestroyRepairOperator(MlPdDestroyPolicy destroyPolicy,
                                   PdExactInsertionOperator exactInsertion,
                                   RegretKPickupDeliveryRepair repair,
                                   PdCrossInsertionOperator crossInsertion,
                                   PdSwapStarOperator swapStar,
                                   TabularMutationScorer tabularScorer,
                                   PdSeedEvaluator evaluator,
                                   PdObjectiveComparator comparator) {
        this.destroyPolicy = destroyPolicy == null ? new MlPdDestroyPolicy() : destroyPolicy;
        this.exactInsertion = exactInsertion == null ? new PdExactInsertionOperator() : exactInsertion;
        this.repair = repair == null ? new RegretKPickupDeliveryRepair() : repair;
        this.crossInsertion = crossInsertion == null ? new PdCrossInsertionOperator() : crossInsertion;
        this.swapStar = swapStar == null ? new PdSwapStarOperator() : swapStar;
        this.tabularScorer = tabularScorer == null ? new TabularMutationScorer() : tabularScorer;
        this.evaluator = evaluator == null ? new PdSeedEvaluator() : evaluator;
        this.comparator = comparator == null ? new PdObjectiveComparator() : comparator;
    }

    public PdLnsResult improve(PdSeedState baseSeed, PdLnsMode mode, int maxRounds, int topBadOrders) {
        PdEvaluation baseEvaluation = evaluator.evaluateSeed(baseSeed);
        if (baseSeed == null || !baseEvaluation.valid()) {
            return new PdLnsResult(false, baseSeed, baseSeed, baseEvaluation, baseEvaluation, 0, 0, 0, 0, 0, List.of());
        }
        PdSeedState current = baseSeed;
        PdEvaluation currentEvaluation = baseEvaluation;
        PdSeedState best = baseSeed;
        PdEvaluation bestEvaluation = baseEvaluation;
        List<PdLnsTrace> traces = new ArrayList<>();
        MlParticipationRecorder mlRecorder = new MlParticipationRecorder();
        int evaluatedOrders = 0;
        int evaluatedInsertions = 0;
        int feasibleInsertions = 0;
        int acceptedMutations = 0;
        int safeRounds = Math.max(1, maxRounds);
        int safeTop = Math.max(2, topBadOrders);
        for (int round = 1; round <= safeRounds; round++) {
            List<Integer> destroySizes = destroySizes(current, mode);
            if (mode.greedRlControlled()) {
                mlRecorder.recordGreedRlAction(destroySizes.size(), true, false);
            }
            List<PdOrderImpact> rankedOrders = rankedOrders(current, mode, round).stream().limit(safeTop).toList();
            for (int destroySize : destroySizes) {
                if (rankedOrders.size() < destroySize) {
                    continue;
                }
                for (List<String> destroyOrders : destroySets(rankedOrders, destroySize, mode)) {
                    if (destroyOrders.size() < destroySize) {
                        continue;
                    }
                    evaluatedOrders += destroyOrders.size();
                    PdSeedState partial = removeOrders(current, destroyOrders);
                    RegretKPickupDeliveryRepair.RepairResult repaired = repair.repair(partial, current, destroyOrders);
                    evaluatedInsertions += repaired.evaluatedInsertions();
                    feasibleInsertions += repaired.feasibleInsertions();
                    PdEvaluation candidateEvaluation = repaired.evaluation();
                    boolean accepted = candidateEvaluation != null
                            && comparator.validNoRegression(candidateEvaluation, currentEvaluation)
                            && betterByMode(mode, currentEvaluation, candidateEvaluation, bestEvaluation, destroyOrders, destroySize, operatorName(destroySize));
                    double reward = reward(currentEvaluation, candidateEvaluation, accepted);
                    if (mode != PdLnsMode.NO_REWARD_UPDATE && mode != PdLnsMode.NO_ADAPTIVE_POLICY) {
                        destroyPolicy.updateReward(destroyOrders, reward);
                    }
                    String operator = "PD_DESTROY_REPAIR_K" + destroySize;
                    if (mode.tabularScored()) {
                        mlRecorder.recordTabularScoring(1, accepted || candidateEvaluation != null, accepted);
                    }
                    if (mode.greedRlControlled()) {
                        mlRecorder.recordGreedRlAction(1, true, accepted);
                    }
                    mlRecorder.recordDecision(
                            "DESTROY_ORDER_SELECTION",
                            operator,
                            rankedOrders.size(),
                            destroyOrders.size(),
                            destroyOrders,
                            selectionSource(mode),
                            1,
                            Math.max(1, rankedOrders.size()),
                            accepted,
                            candidateEvaluation == null ? 0.0 : currentEvaluation.distanceKm() - candidateEvaluation.distanceKm(),
                            reward);
                    if (accepted) {
                        double oldKm = currentEvaluation.distanceKm();
                        current = repaired.seed();
                        currentEvaluation = candidateEvaluation;
                        best = current;
                        bestEvaluation = currentEvaluation;
                        acceptedMutations++;
                        traces.add(new PdLnsTrace(round, String.join(",", destroyOrders), operator, true, oldKm, candidateEvaluation.distanceKm(), round(oldKm - candidateEvaluation.distanceKm()), repaired.evaluatedInsertions(), repaired.feasibleInsertions(), "autoK=" + destroySizes + ";reward=" + round(reward)));
                    } else {
                        String reason = candidateEvaluation == null ? "repair-failed" : candidateEvaluation.rejectReason().isBlank() ? "no-objective-improvement" : candidateEvaluation.rejectReason();
                        traces.add(new PdLnsTrace(round, String.join(",", destroyOrders), operator, false, currentEvaluation.distanceKm(), candidateEvaluation == null ? currentEvaluation.distanceKm() : candidateEvaluation.distanceKm(), 0.0, repaired.evaluatedInsertions(), repaired.feasibleInsertions(), reason + ";autoK=" + destroySizes + ";reward=" + round(reward)));
                    }
                }
            }
        }
        if (mode.hybridPdLns() && mode != PdLnsMode.NO_ADAPTIVE_OPERATOR_POLICY) {
            OperatorApplyResult crossFromBase = applyOperatorResult(crossInsertion.bestMove(baseSeed, safeTop), currentEvaluation, bestEvaluation, safeRounds + 1, traces, mlRecorder, mode);
            OperatorApplyResult swapFromBase = applyOperatorResult(swapStar.bestSwap(baseSeed, safeTop), currentEvaluation, bestEvaluation, safeRounds + 1, traces, mlRecorder, mode);
            OperatorApplyResult crossFromCurrent = applyOperatorResult(crossInsertion.bestMove(current, safeTop), currentEvaluation, bestEvaluation, safeRounds + 1, traces, mlRecorder, mode);
            OperatorApplyResult swapFromCurrent = applyOperatorResult(swapStar.bestSwap(current, safeTop), currentEvaluation, bestEvaluation, safeRounds + 1, traces, mlRecorder, mode);
            for (OperatorApplyResult operatorResult : List.of(crossFromBase, swapFromBase, crossFromCurrent, swapFromCurrent)) {
                evaluatedOrders += operatorResult.evaluatedOrders();
                evaluatedInsertions += operatorResult.evaluatedCandidates();
                feasibleInsertions += operatorResult.feasibleCandidates();
                if (operatorResult.accepted() && comparator.better(operatorResult.evaluation(), bestEvaluation)) {
                    current = operatorResult.seed();
                    currentEvaluation = operatorResult.evaluation();
                    best = current;
                    bestEvaluation = currentEvaluation;
                    acceptedMutations++;
                    if (mode.greedRlControlled()) {
                        mlRecorder.recordGreedRlAction(1, true, true);
                    }
                }
            }
        }
        boolean applied = evaluatedOrders > 0 && evaluatedInsertions > 0;
        return new PdLnsResult(applied, baseSeed, best, baseEvaluation, bestEvaluation, safeRounds, evaluatedOrders, evaluatedInsertions, feasibleInsertions, acceptedMutations, traces, mlRecorder.diagnostics());
    }

    private OperatorApplyResult applyOperatorResult(PdOperatorResult result,
                                                    PdEvaluation currentEvaluation,
                                                    PdEvaluation bestEvaluation,
                                                    int round,
                                                    List<PdLnsTrace> traces,
                                                    MlParticipationRecorder mlRecorder,
                                                    PdLnsMode mode) {
        if (result == null || result.evaluatedCandidates() <= 0) {
            return OperatorApplyResult.empty();
        }
        boolean accepted = result.evaluation() != null
                && comparator.validNoRegression(result.evaluation(), currentEvaluation)
                && comparator.better(result.evaluation(), bestEvaluation);
        if (mode.routefinderAssisted()) {
            mlRecorder.recordRoutefinderCandidates(result.evaluatedCandidates(), true, accepted);
        }
        mlRecorder.recordDecision(
                "OPTIONAL_NEIGHBORHOOD_SELECTION",
                result.operator(),
                result.evaluatedCandidates(),
                result.feasibleCandidates(),
                result.orderIds().isBlank() ? List.of() : List.of(result.orderIds().split(",")),
                "ADAPTIVE_OPERATOR_POLICY",
                1,
                1,
                accepted,
                result.evaluation() == null ? 0.0 : currentEvaluation.distanceKm() - result.evaluation().distanceKm(),
                accepted ? 1.0 : -1.0);
        if (accepted) {
            traces.add(new PdLnsTrace(round, result.orderIds(), result.operator(), true, currentEvaluation.distanceKm(), result.evaluation().distanceKm(), round(currentEvaluation.distanceKm() - result.evaluation().distanceKm()), result.evaluatedCandidates(), result.feasibleCandidates(), "phase5-operator"));
            return new OperatorApplyResult(true, result.seed(), result.evaluation(), result.orderIds().isBlank() ? 0 : result.orderIds().split(",").length, result.evaluatedCandidates(), result.feasibleCandidates());
        }
        traces.add(new PdLnsTrace(round, result.orderIds(), result.operator(), false, currentEvaluation.distanceKm(), result.evaluation() == null ? currentEvaluation.distanceKm() : result.evaluation().distanceKm(), 0.0, result.evaluatedCandidates(), result.feasibleCandidates(), "no-objective-improvement"));
        return new OperatorApplyResult(false, null, null, result.orderIds().isBlank() ? 0 : result.orderIds().split(",").length, result.evaluatedCandidates(), result.feasibleCandidates());
    }

    private record OperatorApplyResult(boolean accepted, PdSeedState seed, PdEvaluation evaluation, int evaluatedOrders, int evaluatedCandidates, int feasibleCandidates) {
        static OperatorApplyResult empty() {
            return new OperatorApplyResult(false, null, null, 0, 0, 0);
        }
    }

    private boolean betterByMode(PdLnsMode mode,
                                 PdEvaluation currentEvaluation,
                                 PdEvaluation candidateEvaluation,
                                 PdEvaluation bestEvaluation,
                                 List<String> orderIds,
                                 int destroySize,
                                 String operator) {
        if (!comparator.better(candidateEvaluation, bestEvaluation)) {
            return false;
        }
        if (!mode.tabularScored()) {
            return true;
        }
        return tabularScorer.score(currentEvaluation, candidateEvaluation, orderIds, destroySize, operator) > 0.0;
    }

    private String operatorName(int destroySize) {
        return "PD_DESTROY_REPAIR_K" + destroySize;
    }

    private List<Integer> destroySizes(PdSeedState seed, PdLnsMode mode) {
        if (mode.greedRlControlled()) {
            int assigned = seed == null ? 0 : seed.assignedCount();
            if (assigned >= 18) {
                return List.of(4, 3, 2);
            }
            if (assigned >= 10) {
                return List.of(3, 4, 2);
            }
            return List.of(2, 3, 4);
        }
        if (mode == PdLnsMode.NO_ADAPTIVE_POLICY || mode == PdLnsMode.NO_ADAPTIVE_OPERATOR_POLICY) {
            return List.of(2, 3, 4);
        }
        if (mode == PdLnsMode.ML_DESTROY_REPAIR_AUTO || mode == PdLnsMode.ML_DESTROY_REPAIR || mode.hybridPdLns()) {
            return List.of(2, 3, 4);
        }
        return List.of(Math.max(2, destroyPolicy.chooseDestroySize(seed, mode)));
    }

    private List<PdOrderImpact> rankedOrders(PdSeedState seed, PdLnsMode mode, int round) {
        if (mode == PdLnsMode.NO_ADAPTIVE_POLICY || mode == PdLnsMode.NO_ADAPTIVE_MOVE_PRIORITY) {
            return new PdOrderImpactAnalyzer().rankBadOrders(seed);
        }
        if (mode == PdLnsMode.NO_ML_RANDOMIZED_PD_LNS) {
            return new PdOrderImpactAnalyzer().rankBadOrders(seed).stream()
                    .sorted((left, right) -> Integer.compare(Math.abs(right.orderId().hashCode() % 997), Math.abs(left.orderId().hashCode() % 997)))
                    .toList();
        }
        return destroyPolicy.rankOrders(seed, round);
    }

    private String selectionSource(PdLnsMode mode) {
        return switch (mode) {
            case NO_ADAPTIVE_POLICY -> "HEURISTIC_ABLATION_NO_ADAPTIVE_POLICY";
            case NO_ADAPTIVE_MOVE_PRIORITY -> "HEURISTIC_ABLATION_NO_MOVE_PRIORITY";
            case NO_ADAPTIVE_OPERATOR_POLICY -> "ADAPTIVE_MOVE_PRIORITY_NO_OPERATOR_POLICY";
            case NO_REWARD_UPDATE -> "ADAPTIVE_MOVE_PRIORITY_NO_REWARD_UPDATE";
            case NO_ML_RANDOMIZED_PD_LNS -> "NO_ML_RANDOMIZED";
            case GREEDRL_CONTROLLER_PD_LNS -> "GREEDRL_OPERATOR_CONTROLLER";
            default -> "ADAPTIVE_MOVE_PRIORITY";
        };
    }

    private List<List<String>> destroySets(List<PdOrderImpact> rankedOrders, int destroySize, PdLnsMode mode) {
        if (mode == PdLnsMode.NO_ADAPTIVE_POLICY || mode == PdLnsMode.NO_ADAPTIVE_MOVE_PRIORITY || mode == PdLnsMode.NO_ML_RANDOMIZED_PD_LNS) {
            List<List<String>> heuristicSets = new ArrayList<>();
            if (rankedOrders.size() >= destroySize) {
                addSet(heuristicSets, rankedOrders.subList(0, destroySize).stream().map(PdOrderImpact::orderId).toList(), destroySize);
            }
            return heuristicSets;
        }
        List<List<String>> sets = new ArrayList<>();
        for (int offset = 0; offset + destroySize <= rankedOrders.size(); offset++) {
            addSet(sets, rankedOrders.subList(offset, offset + destroySize).stream().map(PdOrderImpact::orderId).toList(), destroySize);
        }
        for (int offset = 0; offset < rankedOrders.size() && offset < destroySize; offset++) {
            List<String> diverse = new ArrayList<>();
            diverse.add(rankedOrders.get(offset).orderId());
            for (int index = rankedOrders.size() - 1 - offset; index >= 0 && diverse.size() < destroySize; index--) {
                diverse.add(rankedOrders.get(index).orderId());
            }
            for (int index = destroySize; index < rankedOrders.size() && diverse.size() < destroySize; index += Math.max(1, rankedOrders.size() / destroySize)) {
                diverse.add(rankedOrders.get(index).orderId());
            }
            addSet(sets, diverse, destroySize);
        }
        if (mode.tabularScored()) {
            addTabularExplorationSets(sets, rankedOrders, destroySize, mode);
        }
        if (mode.routefinderAssisted()) {
            addRoutefinderProviderSets(sets, rankedOrders, destroySize);
        }
        return sets;
    }

    private void addRoutefinderProviderSets(List<List<String>> sets, List<PdOrderImpact> rankedOrders, int destroySize) {
        int limit = Math.min(rankedOrders.size(), 12);
        for (int anchor = 0; anchor < limit; anchor++) {
            List<String> routeDiverse = new ArrayList<>();
            routeDiverse.add(rankedOrders.get(anchor).orderId());
            String anchorRoute = rankedOrders.get(anchor).routeId();
            for (int index = 0; index < rankedOrders.size() && routeDiverse.size() < destroySize; index++) {
                PdOrderImpact candidate = rankedOrders.get(index);
                if (!candidate.routeId().equals(anchorRoute)) {
                    routeDiverse.add(candidate.orderId());
                }
            }
            for (int index = rankedOrders.size() - 1; index >= 0 && routeDiverse.size() < destroySize; index--) {
                routeDiverse.add(rankedOrders.get(index).orderId());
            }
            addSet(sets, routeDiverse, destroySize);
            if (sets.size() >= 192) {
                return;
            }
        }
    }

    private void addTabularExplorationSets(List<List<String>> sets, List<PdOrderImpact> rankedOrders, int destroySize, PdLnsMode mode) {
        int limit = Math.min(rankedOrders.size(), mode == PdLnsMode.TABULAR_ONLY_SCORER ? 10 : mode == PdLnsMode.TABULAR_WEIGHT_075 ? 8 : mode == PdLnsMode.TABULAR_WEIGHT_050 ? 6 : 4);
        int maxSets = mode == PdLnsMode.TABULAR_ONLY_SCORER ? 160 : mode == PdLnsMode.TABULAR_WEIGHT_075 ? 128 : mode == PdLnsMode.TABULAR_WEIGHT_050 ? 96 : 64;
        for (int left = 0; left < limit; left++) {
            for (int right = rankedOrders.size() - 1; right >= Math.max(0, rankedOrders.size() - limit) && right > left; right--) {
                List<String> candidate = new ArrayList<>();
                candidate.add(rankedOrders.get(left).orderId());
                candidate.add(rankedOrders.get(right).orderId());
                for (int mid = limit / 2; mid < rankedOrders.size() && candidate.size() < destroySize; mid += Math.max(1, limit / Math.max(1, destroySize))) {
                    candidate.add(rankedOrders.get(mid).orderId());
                }
                addSet(sets, candidate, destroySize);
                if (sets.size() >= maxSets) {
                    return;
                }
            }
        }
    }

    private void addSet(List<List<String>> sets, List<String> orderIds, int destroySize) {
        List<String> unique = new ArrayList<>(new LinkedHashSet<>(orderIds));
        if (unique.size() == destroySize && sets.stream().noneMatch(existing -> existing.equals(unique))) {
            sets.add(unique);
        }
    }

    private PdSeedState removeOrders(PdSeedState seed, List<String> orderIds) {
        Set<String> targets = new LinkedHashSet<>(orderIds == null ? List.of() : orderIds);
        PdSeedState current = seed;
        for (String orderId : targets) {
            current = exactInsertion.removeOrder(current, orderId);
        }
        return current;
    }

    private double reward(PdEvaluation base, PdEvaluation candidate, boolean accepted) {
        if (base == null || candidate == null) {
            return -1000.0;
        }
        double reward = (base.distanceKm() - candidate.distanceKm()) * 100.0
                + (candidate.assignedCount() - base.assignedCount()) * 10000.0
                - Math.max(0, candidate.lateCount() - base.lateCount()) * 1000.0
                - Math.max(0.0, candidate.totalLatenessMinutes() - base.totalLatenessMinutes()) * 100.0
                - Math.max(0, base.assignedCount() - candidate.assignedCount()) * 10000.0
                - candidate.capacityViolations() * 10000.0
                - candidate.pickupDropoffViolations() * 10000.0;
        return accepted ? reward + 10.0 : reward;
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
