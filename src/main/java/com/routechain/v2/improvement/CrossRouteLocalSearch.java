package com.routechain.v2.improvement;

import com.routechain.v2.hybrid.BoundRoute;
import com.routechain.v2.hybrid.BoundStop;
import com.routechain.v2.hybrid.DistanceCostFunction;
import com.routechain.v2.hybrid.LatenessTrace;
import com.routechain.v2.hybrid.MoveEvaluationTrace;
import com.routechain.v2.hybrid.SeedRouteBinding;
import com.routechain.v2.hybrid.StopType;
import com.routechain.v2.schedule.OrderSchedule;
import com.routechain.v2.schedule.RouteSchedule;
import com.routechain.v2.schedule.RouteScheduleEvaluator;
import com.routechain.v2.schedule.SchedulePolicy;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class CrossRouteLocalSearch {
    private static final int MAX_EVALUATED_MOVES = 8;
    private static final int MAX_ORDERS_PER_ROUTE = 8;
    private static final int MAX_ORDERS_PER_ROUTE_TO_TRY = 3;
    private static final int MAX_ROUTE_PAIRS = 6;
    private static final int MAX_ACCEPTED_MOVES = 2;
    private static final long RELOCATE_BUDGET_MS = 500;
    private static final int MAX_SWAP_EVALUATED_MOVES = 6;
    private static final int MAX_SWAP_ACCEPTED_MOVES = 1;
    private static final long SWAP_BUDGET_MS = 350;
    private static final int MAX_INSERTION_POSITIONS = 2;
    private static final int MAX_CROSS_INSERTION_POSITIONS = 3;
    private static final int MAX_CROSS_INSERTION_EVALUATED_MOVES = 6;
    private static final int MAX_CROSS_INSERTION_ACCEPTED_MOVES = 1;
    private static final long CROSS_INSERTION_BUDGET_MS = 350;

    private final RouteScheduleEvaluator evaluator = new RouteScheduleEvaluator();
    private final MoveAcceptancePolicy acceptancePolicy = new MoveAcceptancePolicy();
    private final SchedulePolicy schedulePolicy = SchedulePolicy.defaults();
    private final Map<String, RouteSchedule> routeEvalCache = new LinkedHashMap<>();
    private final Map<String, MoveEvaluationResult> moveEvalCache = new LinkedHashMap<>();
    private final Map<String, Double> legCostCache = new LinkedHashMap<>();
    private int evaluatedMoves;
    private int skippedByBudget;
    private int routeEvalCacheHits;
    private int routeEvalCacheMisses;
    private int moveEvalCacheHits;
    private int moveEvalCacheMisses;
    private int legCacheHits;
    private int legCacheMisses;
    private long startedAtMs;
    private long activeBudgetMs = RELOCATE_BUDGET_MS;
    private boolean budgetExhausted;
    private int routePairsTried;
    private int acceptedMoves;

    public MoveEvaluationResult relocateOnce(SeedRouteBinding binding,
                                             List<BoundRoute> routes,
                                             DistanceCostFunction distanceCost,
                                             boolean feasibleMode) {
        if (binding == null || routes == null || routes.size() < 2 || distanceCost == null) {
            return rejected(null, null, "insufficient-routes");
        }
        resetCaches();
        activeBudgetMs = RELOCATE_BUDGET_MS;
        startedAtMs = System.currentTimeMillis();
        MoveEvaluationResult best = null;
        for (BoundRoute from : routes) {
            if (budgetDone()) {
                break;
            }
            List<String> movableOrders = candidateOrders(from);
            if (movableOrders.size() <= 1 || movableOrders.size() > MAX_ORDERS_PER_ROUTE) {
                continue;
            }
            for (String orderId : movableOrders) {
                if (budgetDone()) {
                    break;
                }
                for (BoundRoute to : routes) {
                    if (from.routeId().equals(to.routeId())) {
                        continue;
                    }
                    if (to.orderIds().size() >= MAX_ORDERS_PER_ROUTE || evaluatedMoves >= MAX_EVALUATED_MOVES || routePairsTried >= MAX_ROUTE_PAIRS || acceptedMoves >= MAX_ACCEPTED_MOVES || budgetDone()) {
                        skippedByBudget++;
                        continue;
                    }
                    routePairsTried++;
                    evaluatedMoves++;
                    MoveEvaluationResult candidate = evaluateInsertion(binding, from, to, orderId, distanceCost, feasibleMode,
                            "RELOCATE_ORDER", "RELOCATE", MAX_INSERTION_POSITIONS);
                    if (candidate.accepted() && (best == null || candidate.newKm() < best.newKm())) {
                        best = candidate;
                        acceptedMoves++;
                        if (best.oldKm() - best.newKm() >= 3.0) {
                            return withStats(best);
                        }
                    }
                }
            }
        }
        return withStats(best == null ? rejected(null, null, "no-accepted-relocate") : best);
    }

    public MoveEvaluationResult crossInsertOnce(SeedRouteBinding binding,
                                                List<BoundRoute> routes,
                                                DistanceCostFunction distanceCost,
                                                boolean feasibleMode) {
        if (binding == null || routes == null || routes.size() < 2 || distanceCost == null) {
            return rejectedWith("INSERT-NONE", null, null, "CROSS_ROUTE_INSERTION", "insufficient-routes");
        }
        resetCaches();
        activeBudgetMs = CROSS_INSERTION_BUDGET_MS;
        startedAtMs = System.currentTimeMillis();
        MoveEvaluationResult best = null;
        for (BoundRoute from : routes) {
            if (budgetDone()) {
                break;
            }
            List<String> movableOrders = candidateOrders(from).stream().limit(2).toList();
            if (movableOrders.isEmpty() || movableOrders.size() > MAX_ORDERS_PER_ROUTE) {
                continue;
            }
            for (String orderId : movableOrders) {
                for (BoundRoute to : routes) {
                    if (from.routeId().equals(to.routeId())) {
                        continue;
                    }
                    if (to.orderIds().size() >= MAX_ORDERS_PER_ROUTE || evaluatedMoves >= MAX_CROSS_INSERTION_EVALUATED_MOVES || routePairsTried >= MAX_ROUTE_PAIRS || acceptedMoves >= MAX_CROSS_INSERTION_ACCEPTED_MOVES || budgetDone()) {
                        skippedByBudget++;
                        continue;
                    }
                    routePairsTried++;
                    evaluatedMoves++;
                    MoveEvaluationResult candidate = evaluateInsertion(binding, from, to, orderId, distanceCost, feasibleMode,
                            "CROSS_ROUTE_INSERTION", "INSERT", MAX_CROSS_INSERTION_POSITIONS);
                    if (candidate.accepted() && (best == null || candidate.newKm() < best.newKm())) {
                        best = candidate;
                        acceptedMoves++;
                    }
                }
            }
        }
        return withStats(best == null ? rejectedWith("INSERT-NONE", null, null, "CROSS_ROUTE_INSERTION", "no-accepted-cross-insertion") : best);
    }

    public MoveEvaluationResult swapOnce(SeedRouteBinding binding,
                                         List<BoundRoute> routes,
                                         DistanceCostFunction distanceCost,
                                         boolean feasibleMode) {
        if (binding == null || routes == null || routes.size() < 2 || distanceCost == null) {
            return rejectedWith("SWAP-NONE", null, null, "SWAP_ORDERS", "insufficient-routes");
        }
        resetCaches();
        activeBudgetMs = SWAP_BUDGET_MS;
        startedAtMs = System.currentTimeMillis();
        MoveEvaluationResult best = null;
        for (BoundRoute routeA : routes) {
            if (budgetDone()) {
                break;
            }
            List<String> ordersA = candidateOrders(routeA).stream().limit(2).toList();
            if (ordersA.isEmpty() || ordersA.size() > MAX_ORDERS_PER_ROUTE) {
                continue;
            }
            for (BoundRoute routeB : routes) {
                if (routeA.routeId().equals(routeB.routeId()) || routePairsTried >= MAX_ROUTE_PAIRS || budgetDone()) {
                    continue;
                }
                List<String> ordersB = candidateOrders(routeB).stream().limit(2).toList();
                for (String orderA : ordersA) {
                    for (String orderB : ordersB) {
                        if (evaluatedMoves >= MAX_SWAP_EVALUATED_MOVES || acceptedMoves >= MAX_SWAP_ACCEPTED_MOVES || budgetDone()) {
                            skippedByBudget++;
                            continue;
                        }
                        routePairsTried++;
                        evaluatedMoves++;
                        MoveEvaluationResult candidate = evaluateSwap(binding, routeA, routeB, orderA, orderB, distanceCost, feasibleMode);
                        if (candidate.accepted() && (best == null || candidate.newKm() < best.newKm())) {
                            best = candidate;
                            acceptedMoves++;
                        }
                    }
                }
            }
        }
        return withStats(best == null ? rejectedWith("SWAP-NONE", null, null, "SWAP_ORDERS", "no-accepted-swap") : best);
    }

    private MoveEvaluationResult evaluateInsertion(SeedRouteBinding binding,
                                                   BoundRoute from,
                                                   BoundRoute to,
                                                   String orderId,
                                                   DistanceCostFunction distanceCost,
                                                   boolean feasibleMode,
                                                   String moveType,
                                                   String movePrefix,
                                                   int maxInsertionPositions) {
        List<BoundStop> fromPath = withoutDriverAndOrder(from, orderId);
        BoundStop pickup = findStop(from, orderId, StopType.PICKUP);
        BoundStop dropoff = findStop(from, orderId, StopType.DROPOFF);
        if (pickup == null || dropoff == null || fromPath.isEmpty()) {
            return rejected(from, to, "missing-relocate-stops");
        }
        List<BoundStop> toBase = withoutDriver(to);
        String moveKey = moveKey(movePrefix, binding, from, to, orderId);
        MoveEvaluationResult cachedMove = moveEvalCache.get(moveKey);
        if (cachedMove != null) {
            moveEvalCacheHits++;
            return cachedMove;
        }
        moveEvalCacheMisses++;
        DistanceCostFunction cachedDistance = cachedDistance(distanceCost, binding.matrixProvider());
        RouteSchedule oldFrom = evaluateRouteCached(from, null, cachedDistance, binding, "relocate-old-from");
        RouteSchedule oldTo = evaluateRouteCached(to, null, cachedDistance, binding, "relocate-old-to");
        RouteSchedule newFrom = evaluateRouteCached(from, fromPath, cachedDistance, binding, "relocate-new-from");
        BoundRoute bestToRoute = null;
        RouteSchedule bestTo = null;
        List<BoundStop> bestToPath = null;
        int insertionEvaluations = 0;
        for (int pickupIndex = 0; pickupIndex <= toBase.size(); pickupIndex++) {
            for (int dropoffIndex = pickupIndex + 1; dropoffIndex <= toBase.size() + 1; dropoffIndex++) {
                if (insertionEvaluations >= maxInsertionPositions || budgetDone()) {
                    skippedByBudget++;
                    break;
                }
                insertionEvaluations++;
                List<BoundStop> candidatePath = new ArrayList<>(toBase);
                candidatePath.add(pickupIndex, pickup);
                candidatePath.add(dropoffIndex, dropoff);
                RouteSchedule candidateSchedule = evaluateRouteCached(to, candidatePath, cachedDistance, binding, "relocate-new-to");
                if (bestTo == null || candidateSchedule.totalKm() < bestTo.totalKm()) {
                    bestTo = candidateSchedule;
                    bestToPath = candidatePath;
                }
            }
        }
        if (bestTo == null || bestToPath == null) {
            MoveEvaluationResult rejected = rejected(from, to, "no-insertion-position");
            moveEvalCache.put(moveKey, rejected);
            return rejected;
        }
        double oldKm = oldFrom.totalKm() + oldTo.totalKm();
        double newKm = newFrom.totalKm() + bestTo.totalKm();
        long oldLate = oldFrom.lateOrderCount() + oldTo.lateOrderCount();
        long newLate = newFrom.lateOrderCount() + bestTo.lateOrderCount();
        double oldLateness = oldFrom.totalLatenessMinutes() + oldTo.totalLatenessMinutes();
        double newLateness = newFrom.totalLatenessMinutes() + bestTo.totalLatenessMinutes();
        boolean accepted = acceptancePolicy.accept(feasibleMode, oldKm, newKm, oldLate, newLate, oldLateness, newLateness);
        String moveId = movePrefix + "-" + orderId + "-" + from.routeId() + "-" + to.routeId();
        String rejectReason = accepted ? "accepted" : rejectReason(feasibleMode, oldKm, newKm, oldLate, newLate, oldLateness, newLateness);
        MoveEvaluationTrace trace = new MoveEvaluationTrace(
                moveId,
                from.routeId() + "->" + to.routeId(),
                moveType,
                round(oldKm),
                round(newKm),
                round(oldKm - newKm),
                accepted,
                rejectReason,
                latenessTraces(moveId, moveType, oldFrom, oldTo, newFrom, bestTo));
        BoundRoute newFromRoute = routeFromSchedule(from, fromPath, newFrom);
        bestToRoute = routeFromSchedule(to, bestToPath, bestTo);
        MoveEvaluationResult result = new MoveEvaluationResult(accepted, newFromRoute, bestToRoute, round(oldKm), round(newKm), oldLate, newLate, round(oldLateness), round(newLateness), List.of(trace), null);
        moveEvalCache.put(moveKey, result);
        return result;
    }

    private MoveEvaluationResult evaluateSwap(SeedRouteBinding binding,
                                              BoundRoute routeA,
                                              BoundRoute routeB,
                                              String orderA,
                                              String orderB,
                                              DistanceCostFunction distanceCost,
                                              boolean feasibleMode) {
        BoundStop pickupA = findStop(routeA, orderA, StopType.PICKUP);
        BoundStop dropoffA = findStop(routeA, orderA, StopType.DROPOFF);
        BoundStop pickupB = findStop(routeB, orderB, StopType.PICKUP);
        BoundStop dropoffB = findStop(routeB, orderB, StopType.DROPOFF);
        if (pickupA == null || dropoffA == null || pickupB == null || dropoffB == null) {
            return rejectedWith("SWAP-NONE", routeA, routeB, "SWAP_ORDERS", "missing-swap-stops");
        }
        String moveKey = swapMoveKey(binding, routeA, routeB, orderA, orderB);
        MoveEvaluationResult cachedMove = moveEvalCache.get(moveKey);
        if (cachedMove != null) {
            moveEvalCacheHits++;
            return cachedMove;
        }
        moveEvalCacheMisses++;
        DistanceCostFunction cachedDistance = cachedDistance(distanceCost, binding.matrixProvider());
        RouteSchedule oldA = evaluateRouteCached(routeA, null, cachedDistance, binding, "swap-old-a");
        RouteSchedule oldB = evaluateRouteCached(routeB, null, cachedDistance, binding, "swap-old-b");
        List<BoundStop> pathA = swapPath(routeA, orderA, pickupB, dropoffB);
        List<BoundStop> pathB = swapPath(routeB, orderB, pickupA, dropoffA);
        RouteSchedule newA = evaluateRouteCached(routeA, pathA, cachedDistance, binding, "swap-new-a");
        RouteSchedule newB = evaluateRouteCached(routeB, pathB, cachedDistance, binding, "swap-new-b");
        double oldKm = oldA.totalKm() + oldB.totalKm();
        double newKm = newA.totalKm() + newB.totalKm();
        long oldLate = oldA.lateOrderCount() + oldB.lateOrderCount();
        long newLate = newA.lateOrderCount() + newB.lateOrderCount();
        double oldLateness = oldA.totalLatenessMinutes() + oldB.totalLatenessMinutes();
        double newLateness = newA.totalLatenessMinutes() + newB.totalLatenessMinutes();
        boolean accepted = acceptancePolicy.accept(feasibleMode, oldKm, newKm, oldLate, newLate, oldLateness, newLateness);
        String moveId = "SWAP-" + orderA + "-" + orderB + "-" + routeA.routeId() + "-" + routeB.routeId();
        String reason = accepted ? "accepted" : rejectReason(feasibleMode, oldKm, newKm, oldLate, newLate, oldLateness, newLateness);
        MoveEvaluationTrace trace = new MoveEvaluationTrace(
                moveId,
                routeA.routeId() + "<->" + routeB.routeId(),
                "SWAP_ORDERS",
                round(oldKm),
                round(newKm),
                round(oldKm - newKm),
                accepted,
                reason,
                latenessTraces(moveId, "SWAP_ORDERS", oldA, oldB, newA, newB));
        MoveEvaluationResult result = new MoveEvaluationResult(
                accepted,
                routeFromSchedule(routeA, pathA, newA),
                routeFromSchedule(routeB, pathB, newB),
                round(oldKm),
                round(newKm),
                oldLate,
                newLate,
                round(oldLateness),
                round(newLateness),
                List.of(trace),
                null);
        moveEvalCache.put(moveKey, result);
        return result;
    }

    private RouteSchedule evaluateRouteCached(BoundRoute route, List<BoundStop> path, DistanceCostFunction distanceCost, SeedRouteBinding binding, String legPrefix) {
        String key = routeKey(route, path, binding.matrixProvider());
        RouteSchedule cached = routeEvalCache.get(key);
        if (cached != null) {
            routeEvalCacheHits++;
            return cached;
        }
        routeEvalCacheMisses++;
        RouteSchedule schedule = evaluator.evaluate(route, path, distanceCost, binding.orderById(), schedulePolicy, legPrefix);
        routeEvalCache.put(key, schedule);
        return schedule;
    }

    private DistanceCostFunction cachedDistance(DistanceCostFunction distanceCost, String matrixProvider) {
        return (legId, fromLat, fromLng, toLat, toLng) -> {
            String key = matrixProvider + ":" + coord(fromLat) + "," + coord(fromLng) + "->" + coord(toLat) + "," + coord(toLng);
            Double cached = legCostCache.get(key);
            if (cached != null) {
                legCacheHits++;
                return cached;
            }
            legCacheMisses++;
            double value = distanceCost.distanceKm(legId, fromLat, fromLng, toLat, toLng);
            legCostCache.put(key, value);
            return value;
        };
    }

    private MoveEvaluationResult withStats(MoveEvaluationResult result) {
        return new MoveEvaluationResult(
                result.accepted(),
                result.fromRoute(),
                result.toRoute(),
                result.oldKm(),
                result.newKm(),
                result.oldLateCount(),
                result.newLateCount(),
                result.oldTotalLatenessMinutes(),
                result.newTotalLatenessMinutes(),
                result.traces(),
                stats());
    }

    private SearchCacheStats stats() {
        return new SearchCacheStats(evaluatedMoves, skippedByBudget, activeBudgetMs, Math.max(0, System.currentTimeMillis() - startedAtMs), budgetExhausted, routeEvalCacheHits, routeEvalCacheMisses, routeEvalCache.size(), moveEvalCacheHits, moveEvalCacheMisses, moveEvalCache.size(), legCacheHits, legCacheMisses, legCostCache.size());
    }

    private void resetCaches() {
        routeEvalCache.clear();
        moveEvalCache.clear();
        legCostCache.clear();
        evaluatedMoves = 0;
        skippedByBudget = 0;
        routeEvalCacheHits = 0;
        routeEvalCacheMisses = 0;
        moveEvalCacheHits = 0;
        moveEvalCacheMisses = 0;
        legCacheHits = 0;
        legCacheMisses = 0;
        budgetExhausted = false;
        routePairsTried = 0;
        acceptedMoves = 0;
    }

    private boolean budgetDone() {
        boolean done = System.currentTimeMillis() - startedAtMs > activeBudgetMs;
        if (done) {
            budgetExhausted = true;
        }
        return done;
    }

    private List<String> candidateOrders(BoundRoute route) {
        return route.orderIds().stream()
                .limit(MAX_ORDERS_PER_ROUTE_TO_TRY)
                .toList();
    }

    private String routeKey(BoundRoute route, List<BoundStop> path, String matrixProvider) {
        List<BoundStop> stops = path == null ? withoutDriver(route) : path;
        String start = route.stops().stream().filter(stop -> stop.type() == StopType.DRIVER_START)
                .map(stop -> coord(stop.location().latitude()) + "," + coord(stop.location().longitude()))
                .findFirst()
                .orElse("no-start");
        String sequence = stops.stream().map(BoundStop::stopId).reduce("", (left, right) -> left + ">" + right);
        return matrixProvider + ":" + schedulePolicy.policyVersion() + ":" + route.driverId() + ":" + start + ":" + sequence;
    }

    private String moveKey(String operator, SeedRouteBinding binding, BoundRoute from, BoundRoute to, String orderId) {
        return operator + ":" + binding.seedId() + ":" + routeKey(from, null, binding.matrixProvider()) + ":" + routeKey(to, null, binding.matrixProvider()) + ":" + orderId + ":" + schedulePolicy.policyVersion();
    }

    private String swapMoveKey(SeedRouteBinding binding, BoundRoute routeA, BoundRoute routeB, String orderA, String orderB) {
        return "SWAP:" + binding.seedId() + ":" + routeKey(routeA, null, binding.matrixProvider()) + ":" + routeKey(routeB, null, binding.matrixProvider()) + ":" + orderA + ":" + orderB + ":" + schedulePolicy.policyVersion();
    }

    private List<LatenessTrace> latenessTraces(String moveId, RouteSchedule oldFrom, RouteSchedule oldTo, RouteSchedule newFrom, RouteSchedule newTo) {
        return latenessTraces(moveId, "RELOCATE_ORDER", oldFrom, oldTo, newFrom, newTo);
    }

    private List<LatenessTrace> latenessTraces(String moveId, String moveType, RouteSchedule oldFrom, RouteSchedule oldTo, RouteSchedule newFrom, RouteSchedule newTo) {
        List<LatenessTrace> traces = new ArrayList<>();
        addLatenessTraces(moveId, moveType, oldFrom, newFrom, traces);
        addLatenessTraces(moveId, moveType, oldTo, newTo, traces);
        return traces;
    }

    private void addLatenessTraces(String moveId, String moveType, RouteSchedule oldSchedule, RouteSchedule newSchedule, List<LatenessTrace> traces) {
        for (OrderSchedule newOrder : newSchedule.orderSchedules().values()) {
            OrderSchedule oldOrder = oldSchedule.orderSchedules().get(newOrder.orderId());
            if (newOrder.late() || (oldOrder != null && newOrder.slackMinutes() < oldOrder.slackMinutes())) {
                traces.add(new LatenessTrace(
                        newSchedule.routeId(),
                        newOrder.orderId(),
                        moveId,
                        moveType,
                        oldOrder == null ? 0.0 : oldOrder.deliveryEtaMinutes(),
                        newOrder.deliveryEtaMinutes(),
                        newOrder.dueTimeMinutes(),
                        oldOrder == null ? 0.0 : oldOrder.slackMinutes(),
                        newOrder.slackMinutes(),
                        newOrder.latenessMinutes(),
                        newOrder.late() ? "relocate-delayed-dropoff" : "relocate-reduced-slack"));
            }
        }
    }

    private BoundRoute routeFromSchedule(BoundRoute original, List<BoundStop> path, RouteSchedule schedule) {
        List<String> orderIds = path.stream().filter(stop -> stop.type() == StopType.PICKUP).map(BoundStop::orderId).distinct().toList();
        List<String> sequence = path.stream().map(stop -> stop.type() + ":" + stop.orderId()).toList();
        List<BoundStop> stops = new ArrayList<>();
        original.stops().stream().filter(stop -> stop.type() == StopType.DRIVER_START).findFirst().ifPresent(stops::add);
        stops.addAll(path);
        return new BoundRoute(original.routeId(), original.driverId(), orderIds, stops, schedule.totalKm(), schedule.durationMinutes(), (int) schedule.lateOrderCount());
    }

    private List<BoundStop> withoutDriver(BoundRoute route) {
        return route.stops().stream().filter(stop -> stop.type() != StopType.DRIVER_START).toList();
    }

    private List<BoundStop> swapPath(BoundRoute route, String removeOrderId, BoundStop incomingPickup, BoundStop incomingDropoff) {
        List<BoundStop> path = new ArrayList<>();
        for (BoundStop stop : withoutDriver(route)) {
            if (!removeOrderId.equals(stop.orderId())) {
                path.add(stop);
                continue;
            }
            if (stop.type() == StopType.PICKUP) {
                path.add(incomingPickup);
            } else if (stop.type() == StopType.DROPOFF) {
                path.add(incomingDropoff);
            }
        }
        return path;
    }

    private List<BoundStop> withoutDriverAndOrder(BoundRoute route, String orderId) {
        return route.stops().stream()
                .filter(stop -> stop.type() != StopType.DRIVER_START)
                .filter(stop -> !orderId.equals(stop.orderId()))
                .toList();
    }

    private BoundStop findStop(BoundRoute route, String orderId, StopType type) {
        return route.stops().stream()
                .filter(stop -> type == stop.type() && orderId.equals(stop.orderId()))
                .findFirst()
                .orElse(null);
    }

    private String rejectReason(boolean feasibleMode, double oldKm, double newKm, long oldLate, long newLate, double oldLateness, double newLateness) {
        if (feasibleMode && newLate > 0) {
            return "late-zero-invariant-violated";
        }
        if (newLate > oldLate) {
            return "late-regression";
        }
        if (newLate == oldLate && newLateness > oldLateness + 0.05) {
            return "total-lateness-regression";
        }
        if (newKm + 0.05 >= oldKm) {
            return "no-distance-improvement";
        }
        return "not-lexicographic-improvement";
    }

    private MoveEvaluationResult rejected(BoundRoute from, BoundRoute to, String reason) {
        return rejectedWith("RELOCATE-NONE", from, to, "RELOCATE_ORDER", reason);
    }

    private MoveEvaluationResult rejectedWith(String moveId, BoundRoute from, BoundRoute to, String moveType, String reason) {
        MoveEvaluationTrace trace = new MoveEvaluationTrace(
                moveId,
                (from == null ? "none" : from.routeId()) + "->" + (to == null ? "none" : to.routeId()),
                moveType,
                0.0,
                0.0,
                0.0,
                false,
                reason,
                List.of());
        return new MoveEvaluationResult(false, from, to, 0.0, 0.0, 0, 0, 0.0, 0.0, List.of(trace), null);
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private String coord(double value) {
        return "%.6f".formatted(value);
    }
}
