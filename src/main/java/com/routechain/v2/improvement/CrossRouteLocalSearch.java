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
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class CrossRouteLocalSearch {
    private static final int MAX_EVALUATED_MOVES = 80;
    private static final int MAX_ORDERS_PER_ROUTE = 8;

    private final RouteScheduleEvaluator evaluator = new RouteScheduleEvaluator();
    private final MoveAcceptancePolicy acceptancePolicy = new MoveAcceptancePolicy();
    private final SchedulePolicy schedulePolicy = SchedulePolicy.defaults();

    public MoveEvaluationResult relocateOnce(SeedRouteBinding binding,
                                             List<BoundRoute> routes,
                                             DistanceCostFunction distanceCost,
                                             boolean feasibleMode) {
        if (binding == null || routes == null || routes.size() < 2 || distanceCost == null) {
            return rejected(null, null, "insufficient-routes");
        }
        MoveEvaluationResult best = null;
        int evaluatedMoves = 0;
        for (BoundRoute from : routes) {
            List<String> movableOrders = from.orderIds();
            if (movableOrders.size() <= 1 || movableOrders.size() > MAX_ORDERS_PER_ROUTE) {
                continue;
            }
            for (String orderId : movableOrders) {
                for (BoundRoute to : routes) {
                    if (from.routeId().equals(to.routeId())) {
                        continue;
                    }
                    if (to.orderIds().size() >= MAX_ORDERS_PER_ROUTE || evaluatedMoves >= MAX_EVALUATED_MOVES) {
                        continue;
                    }
                    evaluatedMoves++;
                    MoveEvaluationResult candidate = evaluateRelocate(binding, from, to, orderId, distanceCost, feasibleMode);
                    if (candidate.accepted() && (best == null || candidate.newKm() < best.newKm())) {
                        best = candidate;
                    }
                }
            }
        }
        return best == null ? rejected(null, null, "no-accepted-relocate") : best;
    }

    private MoveEvaluationResult evaluateRelocate(SeedRouteBinding binding,
                                                  BoundRoute from,
                                                  BoundRoute to,
                                                  String orderId,
                                                  DistanceCostFunction distanceCost,
                                                  boolean feasibleMode) {
        List<BoundStop> fromPath = withoutDriverAndOrder(from, orderId);
        BoundStop pickup = findStop(from, orderId, StopType.PICKUP);
        BoundStop dropoff = findStop(from, orderId, StopType.DROPOFF);
        if (pickup == null || dropoff == null || fromPath.isEmpty()) {
            return rejected(from, to, "missing-relocate-stops");
        }
        List<BoundStop> toBase = withoutDriver(to);
        RouteSchedule oldFrom = evaluator.evaluate(from, null, distanceCost, binding.orderById(), schedulePolicy, "relocate-old-from");
        RouteSchedule oldTo = evaluator.evaluate(to, null, distanceCost, binding.orderById(), schedulePolicy, "relocate-old-to");
        RouteSchedule newFrom = evaluator.evaluate(from, fromPath, distanceCost, binding.orderById(), schedulePolicy, "relocate-new-from");
        BoundRoute bestToRoute = null;
        RouteSchedule bestTo = null;
        List<BoundStop> bestToPath = null;
        for (int pickupIndex = 0; pickupIndex <= toBase.size(); pickupIndex++) {
            for (int dropoffIndex = pickupIndex + 1; dropoffIndex <= toBase.size() + 1; dropoffIndex++) {
                List<BoundStop> candidatePath = new ArrayList<>(toBase);
                candidatePath.add(pickupIndex, pickup);
                candidatePath.add(dropoffIndex, dropoff);
                RouteSchedule candidateSchedule = evaluator.evaluate(to, candidatePath, distanceCost, binding.orderById(), schedulePolicy, "relocate-new-to");
                if (bestTo == null || candidateSchedule.totalKm() < bestTo.totalKm()) {
                    bestTo = candidateSchedule;
                    bestToPath = candidatePath;
                }
            }
        }
        if (bestTo == null || bestToPath == null) {
            return rejected(from, to, "no-insertion-position");
        }
        double oldKm = oldFrom.totalKm() + oldTo.totalKm();
        double newKm = newFrom.totalKm() + bestTo.totalKm();
        long oldLate = oldFrom.lateOrderCount() + oldTo.lateOrderCount();
        long newLate = newFrom.lateOrderCount() + bestTo.lateOrderCount();
        double oldLateness = oldFrom.totalLatenessMinutes() + oldTo.totalLatenessMinutes();
        double newLateness = newFrom.totalLatenessMinutes() + bestTo.totalLatenessMinutes();
        boolean accepted = acceptancePolicy.accept(feasibleMode, oldKm, newKm, oldLate, newLate, oldLateness, newLateness);
        String moveId = "RELOCATE-" + orderId + "-" + from.routeId() + "-" + to.routeId();
        String rejectReason = accepted ? "accepted" : rejectReason(feasibleMode, oldKm, newKm, oldLate, newLate, oldLateness, newLateness);
        MoveEvaluationTrace trace = new MoveEvaluationTrace(
                moveId,
                from.routeId() + "->" + to.routeId(),
                "RELOCATE_ORDER",
                round(oldKm),
                round(newKm),
                round(oldKm - newKm),
                accepted,
                rejectReason,
                latenessTraces(moveId, oldFrom, oldTo, newFrom, bestTo));
        BoundRoute newFromRoute = routeFromSchedule(from, fromPath, newFrom);
        bestToRoute = routeFromSchedule(to, bestToPath, bestTo);
        return new MoveEvaluationResult(accepted, newFromRoute, bestToRoute, round(oldKm), round(newKm), oldLate, newLate, round(oldLateness), round(newLateness), List.of(trace));
    }

    private List<LatenessTrace> latenessTraces(String moveId, RouteSchedule oldFrom, RouteSchedule oldTo, RouteSchedule newFrom, RouteSchedule newTo) {
        List<LatenessTrace> traces = new ArrayList<>();
        addLatenessTraces(moveId, oldFrom, newFrom, traces);
        addLatenessTraces(moveId, oldTo, newTo, traces);
        return traces;
    }

    private void addLatenessTraces(String moveId, RouteSchedule oldSchedule, RouteSchedule newSchedule, List<LatenessTrace> traces) {
        for (OrderSchedule newOrder : newSchedule.orderSchedules().values()) {
            OrderSchedule oldOrder = oldSchedule.orderSchedules().get(newOrder.orderId());
            if (newOrder.late() || (oldOrder != null && newOrder.slackMinutes() < oldOrder.slackMinutes())) {
                traces.add(new LatenessTrace(
                        newSchedule.routeId(),
                        newOrder.orderId(),
                        moveId,
                        "RELOCATE_ORDER",
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
        MoveEvaluationTrace trace = new MoveEvaluationTrace(
                "RELOCATE-NONE",
                (from == null ? "none" : from.routeId()) + "->" + (to == null ? "none" : to.routeId()),
                "RELOCATE_ORDER",
                0.0,
                0.0,
                0.0,
                false,
                reason,
                List.of());
        return new MoveEvaluationResult(false, from, to, 0.0, 0.0, 0, 0, 0.0, 0.0, List.of(trace));
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
