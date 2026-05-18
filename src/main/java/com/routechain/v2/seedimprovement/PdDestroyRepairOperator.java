package com.routechain.v2.seedimprovement;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class PdDestroyRepairOperator {
    private final MlPdDestroyPolicy destroyPolicy;
    private final PdExactInsertionOperator exactInsertion;
    private final RegretKPickupDeliveryRepair repair;
    private final PdSeedEvaluator evaluator;
    private final PdObjectiveComparator comparator;

    public PdDestroyRepairOperator() {
        this(new MlPdDestroyPolicy(), new PdExactInsertionOperator(), new RegretKPickupDeliveryRepair(), new PdSeedEvaluator(), new PdObjectiveComparator());
    }

    public PdDestroyRepairOperator(MlPdDestroyPolicy destroyPolicy,
                                   PdExactInsertionOperator exactInsertion,
                                   RegretKPickupDeliveryRepair repair,
                                   PdSeedEvaluator evaluator,
                                   PdObjectiveComparator comparator) {
        this.destroyPolicy = destroyPolicy == null ? new MlPdDestroyPolicy() : destroyPolicy;
        this.exactInsertion = exactInsertion == null ? new PdExactInsertionOperator() : exactInsertion;
        this.repair = repair == null ? new RegretKPickupDeliveryRepair() : repair;
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
        int evaluatedOrders = 0;
        int evaluatedInsertions = 0;
        int feasibleInsertions = 0;
        int acceptedMutations = 0;
        int safeRounds = Math.max(1, maxRounds);
        int safeTop = Math.max(2, topBadOrders);
        for (int round = 1; round <= safeRounds; round++) {
            List<Integer> destroySizes = destroySizes(current, mode);
            List<PdOrderImpact> rankedOrders = destroyPolicy.rankOrders(current, round).stream().limit(safeTop).toList();
            for (int destroySize : destroySizes) {
                if (rankedOrders.size() < destroySize) {
                    continue;
                }
                for (List<String> destroyOrders : destroySets(rankedOrders, destroySize)) {
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
                            && comparator.better(candidateEvaluation, bestEvaluation);
                    double reward = reward(currentEvaluation, candidateEvaluation, accepted);
                    destroyPolicy.updateReward(destroyOrders, reward);
                    String operator = "PD_DESTROY_REPAIR_K" + destroySize;
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
        boolean applied = evaluatedOrders > 0 && evaluatedInsertions > 0;
        return new PdLnsResult(applied, baseSeed, best, baseEvaluation, bestEvaluation, safeRounds, evaluatedOrders, evaluatedInsertions, feasibleInsertions, acceptedMutations, traces);
    }

    private List<Integer> destroySizes(PdSeedState seed, PdLnsMode mode) {
        if (mode == PdLnsMode.ML_DESTROY_REPAIR_AUTO || mode == PdLnsMode.ML_DESTROY_REPAIR) {
            return List.of(2, 3, 4);
        }
        return List.of(Math.max(2, destroyPolicy.chooseDestroySize(seed, mode)));
    }

    private List<List<String>> destroySets(List<PdOrderImpact> rankedOrders, int destroySize) {
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
        return sets;
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
