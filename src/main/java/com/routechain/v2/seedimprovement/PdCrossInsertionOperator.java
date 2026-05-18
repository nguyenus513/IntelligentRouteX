package com.routechain.v2.seedimprovement;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class PdCrossInsertionOperator {
    private final PdExactInsertionOperator exactInsertion;
    private final PdSeedEvaluator evaluator;
    private final PdObjectiveComparator comparator;

    public PdCrossInsertionOperator() {
        this(new PdExactInsertionOperator(), new PdSeedEvaluator(), new PdObjectiveComparator());
    }

    public PdCrossInsertionOperator(PdExactInsertionOperator exactInsertion, PdSeedEvaluator evaluator, PdObjectiveComparator comparator) {
        this.exactInsertion = exactInsertion == null ? new PdExactInsertionOperator() : exactInsertion;
        this.evaluator = evaluator == null ? new PdSeedEvaluator() : evaluator;
        this.comparator = comparator == null ? new PdObjectiveComparator() : comparator;
    }

    public PdOperatorResult bestMove(PdSeedState seed, int topOrders) {
        PdEvaluation baseline = evaluator.evaluateSeed(seed);
        if (seed == null || seed.routes().size() < 2 || !baseline.valid()) {
            return PdOperatorResult.empty("PD_CROSS_INSERTION");
        }
        PdOperatorResult best = null;
        int evaluated = 0;
        int feasible = 0;
        List<OrderRoute> orders = routeOrders(seed).stream()
                .sorted(Comparator.comparingDouble(order -> -routeDistance(seed, order.routeId())))
                .limit(Math.max(1, topOrders))
                .toList();
        for (OrderRoute order : orders) {
            PdStop pickup = findStop(seed, order.orderId(), PdStop.PdStopType.PICKUP);
            PdStop dropoff = findStop(seed, order.orderId(), PdStop.PdStopType.DROPOFF);
            if (pickup == null || dropoff == null) {
                continue;
            }
            PdSeedState partial = exactInsertion.removeOrder(seed, order.orderId());
            for (PdRouteState route : partial.routes()) {
                if (route.routeId().equals(order.routeId())) {
                    continue;
                }
                int size = route.stops().size();
                for (int pickupPosition = 0; pickupPosition <= size; pickupPosition++) {
                    for (int dropoffPosition = pickupPosition + 1; dropoffPosition <= size + 1; dropoffPosition++) {
                        evaluated++;
                        PdSeedState candidate = exactInsertion.insertIntoRoute(partial, route.routeId(), pickup, dropoff, pickupPosition, dropoffPosition);
                        PdEvaluation evaluation = evaluator.evaluateSeed(candidate);
                        if (!evaluation.valid()) {
                            continue;
                        }
                        feasible++;
                        if (comparator.validNoRegression(evaluation, baseline)
                                && (best == null || comparator.better(evaluation, best.evaluation()))) {
                            best = new PdOperatorResult(candidate, evaluation, "PD_CROSS_INSERTION", order.orderId(), evaluated, feasible);
                        }
                    }
                }
            }
        }
        if (best == null) {
            return new PdOperatorResult(null, null, "PD_CROSS_INSERTION", "", evaluated, feasible);
        }
        return new PdOperatorResult(best.seed(), best.evaluation(), best.operator(), best.orderIds(), evaluated, feasible);
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
}
