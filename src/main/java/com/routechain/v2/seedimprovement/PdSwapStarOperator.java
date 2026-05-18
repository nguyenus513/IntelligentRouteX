package com.routechain.v2.seedimprovement;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class PdSwapStarOperator {
    private final PdExactInsertionOperator exactInsertion;
    private final PdSeedEvaluator evaluator;
    private final PdObjectiveComparator comparator;

    public PdSwapStarOperator() {
        this(new PdExactInsertionOperator(), new PdSeedEvaluator(), new PdObjectiveComparator());
    }

    public PdSwapStarOperator(PdExactInsertionOperator exactInsertion, PdSeedEvaluator evaluator, PdObjectiveComparator comparator) {
        this.exactInsertion = exactInsertion == null ? new PdExactInsertionOperator() : exactInsertion;
        this.evaluator = evaluator == null ? new PdSeedEvaluator() : evaluator;
        this.comparator = comparator == null ? new PdObjectiveComparator() : comparator;
    }

    public PdOperatorResult bestSwap(PdSeedState seed, int topOrders) {
        PdEvaluation baseline = evaluator.evaluateSeed(seed);
        if (seed == null || seed.routes().size() < 2 || !baseline.valid()) {
            return PdOperatorResult.empty("PD_SWAP_STAR");
        }
        List<OrderRoute> orders = routeOrders(seed).stream()
                .sorted(Comparator.comparingDouble(order -> -routeDistance(seed, order.routeId())))
                .limit(Math.max(2, topOrders))
                .toList();
        PdOperatorResult best = null;
        int evaluated = 0;
        int feasible = 0;
        for (int leftIndex = 0; leftIndex < orders.size(); leftIndex++) {
            for (int rightIndex = leftIndex + 1; rightIndex < orders.size(); rightIndex++) {
                OrderRoute left = orders.get(leftIndex);
                OrderRoute right = orders.get(rightIndex);
                if (left.routeId().equals(right.routeId())) {
                    continue;
                }
                PdStop leftPickup = findStop(seed, left.orderId(), PdStop.PdStopType.PICKUP);
                PdStop leftDropoff = findStop(seed, left.orderId(), PdStop.PdStopType.DROPOFF);
                PdStop rightPickup = findStop(seed, right.orderId(), PdStop.PdStopType.PICKUP);
                PdStop rightDropoff = findStop(seed, right.orderId(), PdStop.PdStopType.DROPOFF);
                if (leftPickup == null || leftDropoff == null || rightPickup == null || rightDropoff == null) {
                    continue;
                }
                PdSeedState partial = exactInsertion.removeOrder(exactInsertion.removeOrder(seed, left.orderId()), right.orderId());
                InsertSearch leftInserted = bestInsertIntoRoute(partial, leftPickup, leftDropoff, right.routeId(), left.orderId());
                evaluated += leftInserted.evaluated();
                feasible += leftInserted.feasible();
                if (leftInserted.seed() == null) {
                    continue;
                }
                InsertSearch rightInserted = bestInsertIntoRoute(leftInserted.seed(), rightPickup, rightDropoff, left.routeId(), right.orderId());
                evaluated += rightInserted.evaluated();
                feasible += rightInserted.feasible();
                PdEvaluation evaluation = rightInserted.evaluation();
                if (evaluation != null
                        && comparator.validNoRegression(evaluation, baseline)
                        && (best == null || comparator.better(evaluation, best.evaluation()))) {
                    best = new PdOperatorResult(rightInserted.seed(), evaluation, "PD_SWAP_STAR", left.orderId() + "," + right.orderId(), evaluated, feasible);
                }
            }
        }
        if (best == null) {
            return new PdOperatorResult(null, null, "PD_SWAP_STAR", "", evaluated, feasible);
        }
        return new PdOperatorResult(best.seed(), best.evaluation(), best.operator(), best.orderIds(), evaluated, feasible);
    }

    private InsertSearch bestInsertIntoRoute(PdSeedState seed, PdStop pickup, PdStop dropoff, String routeId, String orderId) {
        PdSeedState bestSeed = null;
        PdEvaluation bestEvaluation = null;
        int evaluated = 0;
        int feasible = 0;
        PdRouteState target = seed.routes().stream().filter(route -> route.routeId().equals(routeId)).findFirst().orElse(null);
        if (target == null) {
            return new InsertSearch(null, null, 0, 0);
        }
        int size = target.stops().size();
        for (int pickupPosition = 0; pickupPosition <= size; pickupPosition++) {
            for (int dropoffPosition = pickupPosition + 1; dropoffPosition <= size + 1; dropoffPosition++) {
                evaluated++;
                PdSeedState candidate = exactInsertion.insertIntoRoute(seed, routeId, pickup, dropoff, pickupPosition, dropoffPosition);
                PdEvaluation evaluation = evaluator.evaluateSeed(candidate);
                if (!evaluation.valid()) {
                    continue;
                }
                feasible++;
                if (bestEvaluation == null || comparator.better(evaluation, bestEvaluation)) {
                    bestSeed = candidate;
                    bestEvaluation = evaluation;
                }
            }
        }
        return new InsertSearch(bestSeed, bestEvaluation, evaluated, feasible);
    }

    private List<OrderRoute> routeOrders(PdSeedState seed) {
        List<OrderRoute> orders = new ArrayList<>();
        for (PdRouteState route : seed.routes()) {
            Set<String> routeOrderIds = new LinkedHashSet<>();
            route.stops().forEach(stop -> routeOrderIds.add(stop.orderId()));
            routeOrderIds.forEach(orderId -> orders.add(new OrderRoute(orderId, route.routeId())));
        }
        return orders;
    }

    private double routeDistance(PdSeedState seed, String routeId) {
        return seed.routes().stream()
                .filter(route -> route.routeId().equals(routeId))
                .findFirst()
                .map(PdRouteState::distanceKm)
                .orElse(0.0);
    }

    private PdStop findStop(PdSeedState seed, String orderId, PdStop.PdStopType type) {
        return seed.routes().stream()
                .flatMap(route -> route.stops().stream())
                .filter(stop -> stop.orderId().equals(orderId) && stop.type() == type)
                .findFirst()
                .orElse(null);
    }

    private record OrderRoute(String orderId, String routeId) {
    }

    private record InsertSearch(PdSeedState seed, PdEvaluation evaluation, int evaluated, int feasible) {
    }
}
