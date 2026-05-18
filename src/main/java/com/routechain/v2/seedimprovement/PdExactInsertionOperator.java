package com.routechain.v2.seedimprovement;

import java.util.ArrayList;
import java.util.List;

public final class PdExactInsertionOperator {
    private final PdSeedEvaluator evaluator;
    private final PdObjectiveComparator comparator;

    public PdExactInsertionOperator() {
        this(new PdSeedEvaluator(), new PdObjectiveComparator());
    }

    public PdExactInsertionOperator(PdSeedEvaluator evaluator, PdObjectiveComparator comparator) {
        this.evaluator = evaluator == null ? new PdSeedEvaluator() : evaluator;
        this.comparator = comparator == null ? new PdObjectiveComparator() : comparator;
    }

    public PdInsertionCandidate bestInsert(PdSeedState seed, String orderId) {
        if (seed == null || orderId == null || orderId.isBlank()) {
            return new PdInsertionCandidate(null, null, orderId, "", -1, -1, 0, 0);
        }
        PdStop pickup = findStop(seed, orderId, PdStop.PdStopType.PICKUP);
        PdStop dropoff = findStop(seed, orderId, PdStop.PdStopType.DROPOFF);
        if (pickup == null || dropoff == null) {
            return new PdInsertionCandidate(null, null, orderId, "", -1, -1, 0, 0);
        }
        PdSeedState partial = removeOrder(seed, orderId);
        PdInsertionCandidate best = null;
        int evaluated = 0;
        int feasible = 0;
        for (PdRouteState route : partial.routes()) {
            int size = route.stops().size();
            for (int pickupPosition = 0; pickupPosition <= size; pickupPosition++) {
                for (int dropoffPosition = pickupPosition + 1; dropoffPosition <= size + 1; dropoffPosition++) {
                    evaluated++;
                    PdSeedState candidate = insertIntoRoute(partial, route.routeId(), pickup, dropoff, pickupPosition, dropoffPosition);
                    PdEvaluation evaluation = evaluator.evaluateSeed(candidate);
                    if (!evaluation.valid()) {
                        continue;
                    }
                    feasible++;
                    if (best == null || comparator.better(evaluation, best.evaluation())) {
                        best = new PdInsertionCandidate(candidate, evaluation, orderId, route.routeId(), pickupPosition, dropoffPosition, evaluated, feasible);
                    }
                }
            }
        }
        if (best == null) {
            return new PdInsertionCandidate(null, null, orderId, "", -1, -1, evaluated, feasible);
        }
        return new PdInsertionCandidate(best.seed(), best.evaluation(), orderId, best.routeId(), best.pickupPosition(), best.dropoffPosition(), evaluated, feasible);
    }

    public PdSeedState removeOrder(PdSeedState seed, String orderId) {
        List<PdRouteState> routes = seed.routes().stream()
                .map(route -> route.withStops(route.stops().stream()
                        .filter(stop -> !stop.orderId().equals(orderId))
                        .toList()))
                .toList();
        return seed.withRoutes(routes);
    }

    public PdSeedState insertIntoRoute(PdSeedState seed, String routeId, PdStop pickup, PdStop dropoff, int pickupPosition, int dropoffPosition) {
        List<PdRouteState> routes = new ArrayList<>();
        for (PdRouteState route : seed.routes()) {
            if (!route.routeId().equals(routeId)) {
                routes.add(route);
                continue;
            }
            List<PdStop> stops = new ArrayList<>(route.stops());
            stops.add(Math.max(0, Math.min(pickupPosition, stops.size())), pickup);
            int safeDropoffPosition = Math.max(pickupPosition + 1, Math.min(dropoffPosition, stops.size()));
            stops.add(safeDropoffPosition, dropoff);
            routes.add(route.withStops(stops));
        }
        return seed.withRoutes(routes);
    }

    private PdStop findStop(PdSeedState seed, String orderId, PdStop.PdStopType type) {
        return seed.routes().stream()
                .flatMap(route -> route.stops().stream())
                .filter(stop -> stop.orderId().equals(orderId) && stop.type() == type)
                .findFirst()
                .orElse(null);
    }
}
