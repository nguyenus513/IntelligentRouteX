package com.routechain.v2.hybrid;

import com.routechain.v2.schedule.OrderSchedule;
import com.routechain.v2.schedule.RouteSchedule;
import com.routechain.v2.schedule.RouteScheduleEvaluator;
import com.routechain.v2.schedule.SchedulePolicy;
import com.routechain.v2.improvement.CrossRouteLocalSearch;
import com.routechain.v2.improvement.MoveEvaluationResult;

import java.util.Comparator;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class EliteMultiStartImprover {
    private final RouteScheduleEvaluator scheduleEvaluator = new RouteScheduleEvaluator();
    private final SchedulePolicy schedulePolicy = SchedulePolicy.defaults();
    private final CrossRouteLocalSearch crossRouteLocalSearch = new CrossRouteLocalSearch();

    public List<ImprovedSolutionCandidate> improve(EliteSolutionArchive archive, int topK) {
        if (archive == null) {
            return List.of();
        }
        return archive.seeds().stream()
                .limit(Math.max(1, topK))
                .map(this::improveSeed)
                .toList();
    }

    public SolutionSeedCandidate bestImprovedOrSeed(EliteSolutionArchive archive, int topK) {
        return improve(archive, topK).stream()
                .map(ImprovedSolutionCandidate::improvedSeed)
                .max(LexicographicSolutionComparator.SLA_STRICT)
                .or(() -> archive == null ? java.util.Optional.empty() : archive.best())
                .orElse(null);
    }

    public List<ImprovedSolutionCandidate> improve(List<SeedRouteBinding> bindings, int topK, DistanceCostFunction distanceCost) {
        if (bindings == null || bindings.isEmpty() || distanceCost == null) {
            return List.of();
        }
        return bindings.stream()
                .limit(Math.max(1, topK))
                .map(binding -> improveBinding(binding, distanceCost))
                .toList();
    }

    private ImprovedSolutionCandidate improveSeed(SolutionSeedCandidate seed) {
        ImprovementTrace trace = new ImprovementTrace(
                seed.source(),
                seed.totalDistanceKm(),
                seed.totalDistanceKm(),
                seed.totalDistanceKm(),
                seed.totalDistanceKm(),
                seed.lateOrderCount(),
                false,
                0,
                0,
                List.of("improvement-engine-skeleton", "no-route-matrix-bound-yet"),
                List.of());
        return new ImprovedSolutionCandidate(seed, seed, trace);
    }

    private ImprovedSolutionCandidate improveBinding(SeedRouteBinding binding, DistanceCostFunction distanceCost) {
        SolutionSeedCandidate seed = binding.seed();
        if (seed == null || binding.routes().isEmpty() || !binding.matrixBound()) {
            return improveSeed(seed == null ? emptySeed(binding) : seed);
        }
        List<String> reasons = new ArrayList<>();
        List<MoveEvaluationTrace> moveTraces = new ArrayList<>();
        reasons.add("routes-bound");
        reasons.add("matrix-bound:" + binding.matrixProvider());
        reasons.add(seed.lateOrderCount() == 0 ? "feasible-improvement-mode" : "recovery-improvement-mode");
        int accepted = 0;
        int rejected = 0;
        List<SolutionSeedRoute> improvedRoutes = new ArrayList<>();
        double totalKm = 0.0;
        long totalLate = 0;
        boolean seedRequiresLateZero = seed.lateOrderCount() == 0;
        for (BoundRoute route : binding.routes()) {
            RouteAttempt attempt = permuteRoute(route, binding, distanceCost, seedRequiresLateZero);
            moveTraces.add(attempt.moveTrace());
            if (attempt.accepted()) {
                accepted++;
                reasons.add("permutation-accepted:" + route.routeId() + ":-" + round(route.distanceKm() - attempt.distanceKm()) + "km");
            } else {
                rejected++;
                reasons.add("permutation-rejected:" + route.routeId() + ":" + attempt.reason());
                if (seedRequiresLateZero && attempt.lateOrders() > 0) {
                    reasons.add("seed-sla-preserved-for-rejected-route:" + route.routeId());
                }
            }
            long routeLate = seedRequiresLateZero && !attempt.accepted() ? 0 : attempt.lateOrders();
            totalKm += attempt.distanceKm();
            totalLate += routeLate;
            improvedRoutes.add(new SolutionSeedRoute(route.routeId(), route.driverId(), attempt.orderIds(), attempt.stopSequence(), attempt.distanceKm(), attempt.durationMinutes(), routeLate));
        }
        totalKm = round(totalKm);
        double coverage = binding.orderById().isEmpty() ? seed.coverageRate() : coveredOrders(improvedRoutes) / (double) binding.orderById().size();
        double score = objective(Math.round(coverage * Math.max(1, binding.orderById().size())), Math.max(1, binding.orderById().size()), totalKm, totalLate);
        SolutionSeedCandidate improved = new SolutionSeedCandidate(
                seed.solutionSeedId() + "-IMPROVED",
                seed.source(),
                improvedRoutes,
                coverage,
                totalKm,
                totalLate,
                improvedRoutes.stream().map(route -> new DriverSeedLoad(route.driverId(), route.orderIds().size())).toList(),
                seed.hardFeasible(),
                seed.hardInvalidReason(),
                seed.softPenaltyReasons(),
                new HybridCostBreakdown(totalKm, totalLate * 10.0, 0.0, 0.0, 0.0, 0.0, score));
        MoveEvaluationResult relocate = crossRouteLocalSearch.relocateOnce(binding, binding.routes(), distanceCost, seedRequiresLateZero);
        if (relocate.accepted()) {
            moveTraces.addAll(relocate.traces());
            reasons.add("relocate-accepted:" + relocate.traces().getFirst().moveId() + ":-" + round(relocate.oldKm() - relocate.newKm()) + "km");
            reasons.add(cacheReason(relocate));
            SolutionSeedCandidate relocateSeed = relocateSeed(seed, binding.routes(), relocate, binding.orderById().size());
            if (LexicographicSolutionComparator.SLA_STRICT.compare(relocateSeed, improved) > 0) {
                improved = relocateSeed;
                totalKm = improved.totalDistanceKm();
                totalLate = improved.lateOrderCount();
            }
        } else {
            moveTraces.addAll(relocate.traces());
            reasons.add("relocate-rejected:" + relocate.traces().getFirst().rejectReason());
            reasons.add(cacheReason(relocate));
        }
        boolean objectiveImproved = LexicographicSolutionComparator.SLA_STRICT.compare(improved, seed) > 0;
        SolutionSeedCandidate selected = objectiveImproved ? improved : seed;
        if (!objectiveImproved) {
            reasons.add("rollback:no-objective-improvement");
        }
        ImprovementTrace trace = new ImprovementTrace(
                seed.source(),
                seed.totalDistanceKm(),
                improved.totalDistanceKm(),
                improved.totalDistanceKm(),
                selected.totalDistanceKm(),
                selected.lateOrderCount(),
                objectiveImproved,
                accepted,
                rejected,
                reasons,
                moveTraces);
        return new ImprovedSolutionCandidate(seed, selected, trace);
    }

    private String cacheReason(MoveEvaluationResult result) {
        var stats = result.cacheStats();
        return "relocate-cache-stats:evaluated=" + stats.evaluatedMoves()
                + ",skippedByBudget=" + stats.skippedByBudget()
                + ",budgetMs=" + stats.budgetMs()
                + ",elapsedMs=" + stats.elapsedMs()
                + ",budgetExhausted=" + stats.budgetExhausted()
                + ",routeHitRate=" + stats.routeEvalCacheHitRate()
                + ",moveHitRate=" + stats.moveEvalCacheHitRate()
                + ",legHitRate=" + stats.legCacheHitRate();
    }

    private SolutionSeedCandidate relocateSeed(SolutionSeedCandidate seed, List<BoundRoute> originalRoutes, MoveEvaluationResult relocate, int inputOrderCount) {
        List<SolutionSeedRoute> routes = originalRoutes.stream()
                .map(route -> {
                    if (relocate.fromRoute() != null && route.routeId().equals(relocate.fromRoute().routeId())) {
                        return solutionRoute(relocate.fromRoute());
                    }
                    if (relocate.toRoute() != null && route.routeId().equals(relocate.toRoute().routeId())) {
                        return solutionRoute(relocate.toRoute());
                    }
                    return solutionRoute(route);
                })
                .toList();
        double totalKm = routes.stream().mapToDouble(SolutionSeedRoute::distanceKm).sum();
        long totalLate = routes.stream().mapToLong(SolutionSeedRoute::lateOrderCount).sum();
        double coverage = inputOrderCount <= 0 ? seed.coverageRate() : coveredOrders(routes) / (double) inputOrderCount;
        double score = objective(Math.round(coverage * Math.max(1, inputOrderCount)), Math.max(1, inputOrderCount), totalKm, totalLate);
        return new SolutionSeedCandidate(
                seed.solutionSeedId() + "-RELOCATED",
                seed.source(),
                routes,
                coverage,
                round(totalKm),
                totalLate,
                routes.stream().map(route -> new DriverSeedLoad(route.driverId(), route.orderIds().size())).toList(),
                seed.hardFeasible(),
                seed.hardInvalidReason(),
                seed.softPenaltyReasons(),
                new HybridCostBreakdown(round(totalKm), totalLate * 10.0, 0.0, 0.0, 0.0, 0.0, score));
    }

    private SolutionSeedRoute solutionRoute(BoundRoute route) {
        return new SolutionSeedRoute(
                route.routeId(),
                route.driverId(),
                route.orderIds(),
                route.stops().stream().filter(stop -> stop.type() != StopType.DRIVER_START).map(stop -> stop.type() + ":" + stop.orderId()).toList(),
                route.distanceKm(),
                route.durationMinutes(),
                route.lateOrderCount());
    }

    private RouteAttempt permuteRoute(BoundRoute route, SeedRouteBinding binding, DistanceCostFunction distanceCost, boolean seedRequiresLateZero) {
        List<BoundStop> pickups = route.stops().stream().filter(stop -> stop.type() == StopType.PICKUP).toList();
        List<BoundStop> dropoffs = route.stops().stream().filter(stop -> stop.type() == StopType.DROPOFF).toList();
        if (pickups.isEmpty() || pickups.size() != dropoffs.size() || pickups.size() > 5) {
            return originalRoute(route, binding, distanceCost, "unsupported-route-size");
        }
        BoundStop driverStart = route.stops().stream().filter(stop -> stop.type() == StopType.DRIVER_START).findFirst().orElse(null);
        if (driverStart == null) {
            return originalRoute(route, binding, distanceCost, "missing-driver-start");
        }
        List<BoundStop> candidates = new ArrayList<>();
        candidates.addAll(pickups);
        candidates.addAll(dropoffs);
        List<BoundStop> bestPath = new ArrayList<>();
        double[] bestCost = {Double.POSITIVE_INFINITY};
        search(driverStart, candidates, new ArrayList<>(), new LinkedHashSet<>(), new LinkedHashSet<>(), 0.0, bestCost, bestPath, distanceCost);
        if (bestPath.isEmpty()) {
            return originalRoute(route, binding, distanceCost, "no-valid-permutation");
        }
        RouteAttempt original = originalRoute(route, binding, distanceCost, "baseline-route");
        RouteAttempt attempt = routeAttempt(route, driverStart, bestPath, binding, distanceCost, "permutation-attempted");
        MoveEvaluationTrace trace = moveTrace(route, original, attempt, route.lateOrderCount(), seedRequiresLateZero);
        if (trace.accepted()) {
            return new RouteAttempt(true, attempt.orderIds(), attempt.stopSequence(), attempt.distanceKm(), attempt.durationMinutes(), attempt.lateOrders(), "objective-improved", trace);
        }
        return withTrace(original, trace);
    }

    private void search(BoundStop current, List<BoundStop> candidates, List<BoundStop> path, Set<String> visitedStops, Set<String> pickedOrders, double cost, double[] bestCost, List<BoundStop> bestPath, DistanceCostFunction distanceCost) {
        if (cost >= bestCost[0]) {
            return;
        }
        if (path.size() == candidates.size()) {
            bestCost[0] = cost;
            bestPath.clear();
            bestPath.addAll(path);
            return;
        }
        for (BoundStop next : candidates) {
            if (visitedStops.contains(next.stopId())) {
                continue;
            }
            if (next.type() == StopType.DROPOFF && !pickedOrders.contains(next.orderId())) {
                continue;
            }
            double leg = distanceCost.distanceKm("hybrid-permute-" + current.stopId() + "-" + next.stopId(), current.location().latitude(), current.location().longitude(), next.location().latitude(), next.location().longitude());
            path.add(next);
            visitedStops.add(next.stopId());
            boolean addedPickup = next.type() == StopType.PICKUP && pickedOrders.add(next.orderId());
            search(next, candidates, path, visitedStops, pickedOrders, cost + leg, bestCost, bestPath, distanceCost);
            if (addedPickup) {
                pickedOrders.remove(next.orderId());
            }
            visitedStops.remove(next.stopId());
            path.remove(path.size() - 1);
        }
    }

    private RouteAttempt originalRoute(BoundRoute route, SeedRouteBinding binding, DistanceCostFunction distanceCost, String reason) {
        BoundStop start = route.stops().stream().filter(stop -> stop.type() == StopType.DRIVER_START).findFirst().orElse(null);
        List<BoundStop> path = route.stops().stream().filter(stop -> stop.type() != StopType.DRIVER_START).toList();
        return start == null ? new RouteAttempt(false, route.orderIds(), route.stops().stream().map(stop -> stop.type() + ":" + stop.orderId()).toList(), route.distanceKm(), route.durationMinutes(), route.lateOrderCount(), reason, emptyMoveTrace(route, reason))
                : routeAttempt(route, start, path, binding, distanceCost, reason);
    }

    private RouteAttempt routeAttempt(BoundRoute route, BoundStop start, List<BoundStop> path, SeedRouteBinding binding, DistanceCostFunction distanceCost, String reason) {
        RouteSchedule oldSchedule = scheduleEvaluator.evaluate(route, null, distanceCost, binding.orderById(), schedulePolicy, "hybrid-old-schedule");
        RouteSchedule newSchedule = scheduleEvaluator.evaluate(route, path, distanceCost, binding.orderById(), schedulePolicy, "hybrid-new-schedule");
        List<LatenessTrace> lateTraces = new ArrayList<>();
        for (OrderSchedule newOrder : newSchedule.orderSchedules().values()) {
            OrderSchedule oldOrder = oldSchedule.orderSchedules().get(newOrder.orderId());
            if (newOrder.late() || (oldOrder != null && newOrder.slackMinutes() < oldOrder.slackMinutes())) {
                lateTraces.add(new LatenessTrace(
                        route.routeId(),
                        newOrder.orderId(),
                        "PERM-" + route.routeId(),
                        "PERMUTATION",
                        oldOrder == null ? 0.0 : oldOrder.deliveryEtaMinutes(),
                        newOrder.deliveryEtaMinutes(),
                        newOrder.dueTimeMinutes(),
                        oldOrder == null ? 0.0 : oldOrder.slackMinutes(),
                        newOrder.slackMinutes(),
                        newOrder.latenessMinutes(),
                        newOrder.late() ? "candidate-dropoff-after-due-time" : "candidate-slack-reduced"));
            }
        }
        List<String> orderIds = path.stream().filter(stop -> stop.type() == StopType.PICKUP).map(BoundStop::orderId).distinct().toList();
        List<String> sequence = path.stream().map(stop -> stop.type() + ":" + stop.orderId()).toList();
        MoveEvaluationTrace trace = new MoveEvaluationTrace(
                "PERM-" + route.routeId(),
                route.routeId(),
                "PERMUTATION",
                oldSchedule.totalKm(),
                newSchedule.totalKm(),
                round(oldSchedule.totalKm() - newSchedule.totalKm()),
                false,
                reason,
                lateTraces);
        return new RouteAttempt(false, orderIds, sequence, newSchedule.totalKm(), newSchedule.durationMinutes(), newSchedule.lateOrderCount(), reason, trace);
    }

    private MoveEvaluationTrace moveTrace(BoundRoute route, RouteAttempt original, RouteAttempt candidate, int baselineLateCount, boolean seedRequiresLateZero) {
        String rejectReason = "accepted";
        boolean accepted = false;
        if (seedRequiresLateZero && candidate.lateOrders() > 0) {
            rejectReason = "late-zero-invariant-violated";
        } else if (candidate.lateOrders() > baselineLateCount) {
            rejectReason = "sla-regression";
        } else if (candidate.distanceKm() + 0.05 >= Math.max(0.0, original.distanceKm())) {
            rejectReason = "no-distance-improvement";
        } else {
            accepted = true;
        }
        return new MoveEvaluationTrace(
                "PERM-" + route.routeId(),
                route.routeId(),
                "PERMUTATION",
                original.distanceKm(),
                candidate.distanceKm(),
                round(original.distanceKm() - candidate.distanceKm()),
                accepted,
                rejectReason,
                candidate.moveTrace().latenessTrace());
    }

    private RouteAttempt withTrace(RouteAttempt attempt, MoveEvaluationTrace trace) {
        return new RouteAttempt(false, attempt.orderIds(), attempt.stopSequence(), attempt.distanceKm(), attempt.durationMinutes(), attempt.lateOrders(), trace.rejectReason(), trace);
    }

    private MoveEvaluationTrace emptyMoveTrace(BoundRoute route, String reason) {
        return new MoveEvaluationTrace("PERM-" + route.routeId(), route.routeId(), "PERMUTATION", route.distanceKm(), route.distanceKm(), 0.0, false, reason, List.of());
    }

    private int coveredOrders(List<SolutionSeedRoute> routes) {
        return (int) routes.stream().flatMap(route -> route.orderIds().stream()).distinct().count();
    }

    private double objective(long assignedOrders, long inputOrders, double distanceKm, long lateOrders) {
        long safeInput = Math.max(1, inputOrders);
        return (assignedOrders / (double) safeInput) * 1_000_000.0 - Math.max(0, inputOrders - assignedOrders) * 1_000_000.0 - distanceKm * 100.0 - lateOrders * 10_000.0;
    }

    private SolutionSeedCandidate emptySeed(SeedRouteBinding binding) {
        return new SolutionSeedCandidate(binding.seedId(), binding.source(), List.of(), 0.0, 0.0, 0, List.of(), false, "missing-seed", List.of("missing-seed"), new HybridCostBreakdown(0, 0, 0, 0, 0, 0, -1_000_000));
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private record RouteAttempt(boolean accepted, List<String> orderIds, List<String> stopSequence, double distanceKm, double durationMinutes, long lateOrders, String reason, MoveEvaluationTrace moveTrace) {
    }
}
