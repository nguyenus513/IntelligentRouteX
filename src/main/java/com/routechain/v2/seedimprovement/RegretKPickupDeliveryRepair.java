package com.routechain.v2.seedimprovement;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class RegretKPickupDeliveryRepair {
    private final PdExactInsertionOperator exactInsertion;
    private final MlPdMutationRanker mutationRanker;
    private final PdSeedEvaluator evaluator;

    public RegretKPickupDeliveryRepair() {
        this(new PdExactInsertionOperator(), new MlPdMutationRanker(), new PdSeedEvaluator());
    }

    public RegretKPickupDeliveryRepair(PdExactInsertionOperator exactInsertion, MlPdMutationRanker mutationRanker, PdSeedEvaluator evaluator) {
        this.exactInsertion = exactInsertion == null ? new PdExactInsertionOperator() : exactInsertion;
        this.mutationRanker = mutationRanker == null ? new MlPdMutationRanker() : mutationRanker;
        this.evaluator = evaluator == null ? new PdSeedEvaluator() : evaluator;
    }

    public RepairResult repair(PdSeedState partial, PdSeedState template, List<String> orderIds) {
        PdSeedState current = partial;
        List<String> remaining = new ArrayList<>(orderIds == null ? List.of() : orderIds);
        int evaluated = 0;
        int feasible = 0;
        while (!remaining.isEmpty()) {
            List<PdInsertionCandidate> candidates = new ArrayList<>();
            for (String orderId : remaining) {
                OrderInsertionSearch search = bestInsertFromTemplate(current, template, orderId);
                evaluated += search.evaluated();
                feasible += search.feasible();
                candidates.addAll(search.candidates());
            }
            List<PdInsertionCandidate> ranked = mutationRanker.rankInsertions(candidates);
            if (ranked.isEmpty()) {
                return new RepairResult(null, null, evaluated, feasible, remaining.size());
            }
            PdInsertionCandidate selected = ranked.stream()
                    .min(Comparator.comparingDouble(candidate -> candidate.evaluation().distanceKm()))
                    .orElse(ranked.get(0));
            current = selected.seed();
            remaining.remove(selected.orderId());
        }
        PdEvaluation evaluation = new PdSeedEvaluator().evaluateSeed(current);
        return new RepairResult(current, evaluation, evaluated, feasible, 0);
    }

    private OrderInsertionSearch bestInsertFromTemplate(PdSeedState seed, PdSeedState template, String orderId) {
        PdStop pickup = findStop(template, orderId, PdStop.PdStopType.PICKUP);
        PdStop dropoff = findStop(template, orderId, PdStop.PdStopType.DROPOFF);
        if (pickup == null || dropoff == null) {
            return new OrderInsertionSearch(List.of(), 0, 0);
        }
        List<PdInsertionCandidate> candidates = new ArrayList<>();
        int evaluated = 0;
        int feasible = 0;
        for (PdRouteState route : seed.routes()) {
            int size = route.stops().size();
            for (int pickupPosition = 0; pickupPosition <= size; pickupPosition++) {
                for (int dropoffPosition = pickupPosition + 1; dropoffPosition <= size + 1; dropoffPosition++) {
                    evaluated++;
                    PdSeedState candidateSeed = exactInsertion.insertIntoRoute(seed, route.routeId(), pickup, dropoff, pickupPosition, dropoffPosition);
                    PdEvaluation evaluation = evaluator.evaluateSeed(candidateSeed);
                    if (!evaluation.valid()) {
                        continue;
                    }
                    feasible++;
                    candidates.add(new PdInsertionCandidate(candidateSeed, evaluation, orderId, route.routeId(), pickupPosition, dropoffPosition, evaluated, feasible));
                }
            }
        }
        return new OrderInsertionSearch(candidates, evaluated, feasible);
    }

    private PdStop findStop(PdSeedState seed, String orderId, PdStop.PdStopType type) {
        if (seed == null) {
            return null;
        }
        return seed.routes().stream()
                .flatMap(route -> route.stops().stream())
                .filter(stop -> stop.orderId().equals(orderId) && stop.type() == type)
                .findFirst()
                .orElse(null);
    }

    private record OrderInsertionSearch(List<PdInsertionCandidate> candidates, int evaluated, int feasible) {
    }

    public record RepairResult(PdSeedState seed, PdEvaluation evaluation, int evaluatedInsertions, int feasibleInsertions, int unrepairedOrders) {
    }
}
