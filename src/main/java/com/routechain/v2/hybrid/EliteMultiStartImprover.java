package com.routechain.v2.hybrid;

import com.routechain.v2.schedule.OrderSchedule;
import com.routechain.v2.schedule.RouteSchedule;
import com.routechain.v2.schedule.RouteScheduleEvaluator;
import com.routechain.v2.schedule.SchedulePolicy;
import com.routechain.v2.improvement.CrossRouteLocalSearch;
import com.routechain.v2.improvement.MoveEvaluationResult;
import com.routechain.v2.mladaptive.AdaptiveMlPolicyConfig;
import com.routechain.v2.mladaptive.AdaptiveMlPolicyMode;

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
        return improve(bindings, topK, distanceCost, false);
    }

    public List<ImprovedSolutionCandidate> improve(List<SeedRouteBinding> bindings, int topK, DistanceCostFunction distanceCost, boolean swapStarEnabled) {
        return improve(bindings, topK, distanceCost, swapStarEnabled, AdaptiveMlPolicyConfig.diagnostic());
    }

    public List<ImprovedSolutionCandidate> improve(List<SeedRouteBinding> bindings, int topK, DistanceCostFunction distanceCost, boolean swapStarEnabled, AdaptiveMlPolicyConfig adaptiveConfig) {
        if (bindings == null || bindings.isEmpty() || distanceCost == null) {
            return List.of();
        }
        return bindings.stream()
                .limit(Math.max(1, topK))
                .map(binding -> improveBinding(binding, distanceCost, swapStarEnabled, adaptiveConfig == null ? AdaptiveMlPolicyConfig.diagnostic() : adaptiveConfig))
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

    private ImprovedSolutionCandidate improveBinding(SeedRouteBinding binding, DistanceCostFunction distanceCost, boolean swapStarEnabled, AdaptiveMlPolicyConfig adaptiveConfig) {
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
            RouteAttempt attempt = permuteRoute(route, binding, distanceCost, seedRequiresLateZero, adaptiveConfig);
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
        MoveEvaluationResult relocate = crossRouteLocalSearch.relocateOnce(binding, binding.routes(), distanceCost, seedRequiresLateZero, adaptiveConfig);
        if (relocate.accepted()) {
            moveTraces.addAll(relocate.traces());
            reasons.add("relocate-accepted:" + relocate.traces().getFirst().moveId() + ":-" + round(relocate.oldKm() - relocate.newKm()) + "km");
            reasons.add(cacheReason("relocate", relocate));
            SolutionSeedCandidate relocateSeed = moveSeed(seed, binding.routes(), relocate, binding.orderById().size(), "RELOCATED");
            if (LexicographicSolutionComparator.SLA_STRICT.compare(relocateSeed, improved) > 0) {
                improved = relocateSeed;
                totalKm = improved.totalDistanceKm();
                totalLate = improved.lateOrderCount();
            }
        } else {
            moveTraces.addAll(relocate.traces());
            reasons.add("relocate-rejected:" + relocate.traces().getFirst().rejectReason());
            reasons.add(cacheReason("relocate", relocate));
        }
        MoveEvaluationResult swap = crossRouteLocalSearch.swapOnce(binding, binding.routes(), distanceCost, seedRequiresLateZero, adaptiveConfig);
        if (swap.accepted()) {
            moveTraces.addAll(swap.traces());
            reasons.add("swap-accepted:" + swap.traces().getFirst().moveId() + ":-" + round(swap.oldKm() - swap.newKm()) + "km");
            reasons.add(cacheReason("swap", swap));
            SolutionSeedCandidate swapSeed = moveSeed(seed, binding.routes(), swap, binding.orderById().size(), "SWAPPED");
            if (LexicographicSolutionComparator.SLA_STRICT.compare(swapSeed, improved) > 0) {
                improved = swapSeed;
                totalKm = improved.totalDistanceKm();
                totalLate = improved.lateOrderCount();
            }
        } else {
            moveTraces.addAll(swap.traces());
            reasons.add("swap-rejected:" + swap.traces().getFirst().rejectReason());
            reasons.add(cacheReason("swap", swap));
        }
        MoveEvaluationResult crossInsert = crossRouteLocalSearch.crossInsertOnce(binding, binding.routes(), distanceCost, seedRequiresLateZero, adaptiveConfig);
        if (crossInsert.accepted()) {
            moveTraces.addAll(crossInsert.traces());
            reasons.add("cross-insertion-accepted:" + crossInsert.traces().getFirst().moveId() + ":-" + round(crossInsert.oldKm() - crossInsert.newKm()) + "km");
            reasons.add(cacheReason("cross-insertion", crossInsert));
            SolutionSeedCandidate insertedSeed = moveSeed(seed, binding.routes(), crossInsert, binding.orderById().size(), "INSERTED");
            if (LexicographicSolutionComparator.SLA_STRICT.compare(insertedSeed, improved) > 0) {
                improved = insertedSeed;
                totalKm = improved.totalDistanceKm();
                totalLate = improved.lateOrderCount();
            }
        } else {
            moveTraces.addAll(crossInsert.traces());
            reasons.add("cross-insertion-rejected:" + crossInsert.traces().getFirst().rejectReason());
            reasons.add(cacheReason("cross-insertion", crossInsert));
        }
        if (swapStarEnabled) {
            MoveEvaluationResult swapStar = crossRouteLocalSearch.swapStarOnce(binding, binding.routes(), distanceCost, seedRequiresLateZero, adaptiveConfig);
            if (swapStar.accepted()) {
                moveTraces.addAll(swapStar.traces());
                reasons.add("swap-star-accepted:" + swapStar.traces().getFirst().moveId() + ":-" + round(swapStar.oldKm() - swapStar.newKm()) + "km");
                reasons.add(cacheReason("swap-star", swapStar));
                SolutionSeedCandidate swapStarSeed = moveSeed(seed, binding.routes(), swapStar, binding.orderById().size(), "SWAPSTAR");
                if (LexicographicSolutionComparator.SLA_STRICT.compare(swapStarSeed, improved) > 0) {
                    improved = swapStarSeed;
                    totalKm = improved.totalDistanceKm();
                    totalLate = improved.lateOrderCount();
                }
            } else {
                moveTraces.addAll(swapStar.traces());
                reasons.add("swap-star-rejected:" + swapStar.traces().getFirst().rejectReason());
                reasons.add(cacheReason("swap-star", swapStar));
            }
        } else {
            reasons.add("swap-star-skipped:fast-gate-disabled");
        }
        if (seed.source() == CandidateSource.VROOM_SEED) {
            VroomIntensifierResult vroomSplit = vroomSplitToBestDriver(seed, binding, improved, distanceCost, seedRequiresLateZero);
            moveTraces.add(vroomSplit.trace());
            reasons.add(vroomSplit.reason());
            if (LexicographicSolutionComparator.SLA_STRICT.compare(vroomSplit.candidate(), improved) > 0) {
                improved = vroomSplit.candidate();
                totalKm = improved.totalDistanceKm();
                totalLate = improved.lateOrderCount();
                accepted++;
            } else {
                rejected++;
            }
        }
        boolean objectiveImproved = LexicographicSolutionComparator.SLA_STRICT.compare(improved, seed) > 0;
        SolutionSeedCandidate selected = objectiveImproved ? improved : seed;
        if (adaptiveConfig.assistedControl()) {
            ImprovedSolutionCandidate fallback = improveBinding(binding, distanceCost, swapStarEnabled, AdaptiveMlPolicyConfig.diagnostic());
            if (fallback != null && LexicographicSolutionComparator.SLA_STRICT.compare(fallback.improvedSeed(), selected) > 0) {
                return fallback;
            }
        }
        if (!objectiveImproved) {
            reasons.add("rollback:no-objective-improvement");
        }
        ImprovementTrace trace = new ImprovementTrace(
                improvedSource(seed, selected),
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
        return new ImprovedSolutionCandidate(seed, withImprovedSource(seed, selected), trace);
    }

    private String cacheReason(String operator, MoveEvaluationResult result) {
        var stats = result.cacheStats();
        return operator + "-cache-stats:evaluated=" + stats.evaluatedMoves()
                + ",skippedByBudget=" + stats.skippedByBudget()
                + ",budgetMs=" + stats.budgetMs()
                + ",elapsedMs=" + stats.elapsedMs()
                + ",budgetExhausted=" + stats.budgetExhausted()
                + ",routeHitRate=" + stats.routeEvalCacheHitRate()
                + ",moveHitRate=" + stats.moveEvalCacheHitRate()
                + ",legHitRate=" + stats.legCacheHitRate();
    }

    private SolutionSeedCandidate moveSeed(SolutionSeedCandidate seed, List<BoundRoute> originalRoutes, MoveEvaluationResult relocate, int inputOrderCount, String suffix) {
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
                seed.solutionSeedId() + "-" + suffix,
                improvedSource(seed, relocate),
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

    private VroomIntensifierResult vroomSplitToBestDriver(SolutionSeedCandidate seed,
                                                          SeedRouteBinding binding,
                                                          SolutionSeedCandidate incumbent,
                                                          DistanceCostFunction distanceCost,
                                                          boolean seedRequiresLateZero) {
        SolutionSeedCandidate best = incumbent;
        MoveEvaluationTrace bestTrace = null;
        String bestReason = "vroom-split-rejected:no-improving-feasible-split";
        VroomIntensifierResult subsetSplit = vroomSubsetSplitToEmptyDriver(seed, binding, best, distanceCost, seedRequiresLateZero);
        if (LexicographicSolutionComparator.SLA_STRICT.compare(subsetSplit.candidate(), best) > 0) {
            best = subsetSplit.candidate();
            bestTrace = subsetSplit.trace();
            bestReason = subsetSplit.reason();
        }
        for (BoundRoute from : binding.routes()) {
            if (from.orderIds().isEmpty()) {
                continue;
            }
            for (String orderId : from.orderIds()) {
                BoundStop pickup = findStop(from, orderId, StopType.PICKUP);
                BoundStop dropoff = findStop(from, orderId, StopType.DROPOFF);
                if (pickup == null || dropoff == null) {
                    continue;
                }
                List<BoundStop> fromPath = withoutDriverAndOrder(from, orderId);
                RouteSchedule oldFrom = scheduleEvaluator.evaluate(from, null, distanceCost, binding.orderById(), schedulePolicy, "vroom-split-old-from");
                RouteSchedule newFrom = scheduleEvaluator.evaluate(from, fromPath, distanceCost, binding.orderById(), schedulePolicy, "vroom-split-new-from");
                for (BoundRoute to : binding.routes()) {
                    if (from.routeId().equals(to.routeId())) {
                        continue;
                    }
                    List<BoundStop> toBase = withoutDriver(to);
                    RouteSchedule oldTo = scheduleEvaluator.evaluate(to, null, distanceCost, binding.orderById(), schedulePolicy, "vroom-split-old-to");
                    for (int pickupIndex = 0; pickupIndex <= toBase.size(); pickupIndex++) {
                        for (int dropoffIndex = pickupIndex + 1; dropoffIndex <= toBase.size() + 1; dropoffIndex++) {
                            List<BoundStop> toPath = new ArrayList<>(toBase);
                            toPath.add(pickupIndex, pickup);
                            toPath.add(dropoffIndex, dropoff);
                            RouteSchedule newTo = scheduleEvaluator.evaluate(to, toPath, distanceCost, binding.orderById(), schedulePolicy, "vroom-split-new-to");
                            long newLate = binding.routes().stream()
                                    .filter(route -> !route.routeId().equals(from.routeId()) && !route.routeId().equals(to.routeId()))
                                    .mapToLong(BoundRoute::lateOrderCount)
                                    .sum() + newFrom.lateOrderCount() + newTo.lateOrderCount();
                            if (seedRequiresLateZero && newLate > 0) {
                                continue;
                            }
                            double newKm = binding.routes().stream()
                                    .filter(route -> !route.routeId().equals(from.routeId()) && !route.routeId().equals(to.routeId()))
                                    .mapToDouble(BoundRoute::distanceKm)
                                    .sum() + newFrom.totalKm() + newTo.totalKm();
                            if (round(newKm) + 0.05 >= Math.min(best.totalDistanceKm(), seed.totalDistanceKm())) {
                                continue;
                            }
                            BoundRoute newFromRoute = routeFromSchedule(from, fromPath, newFrom);
                            BoundRoute newToRoute = routeFromSchedule(to, toPath, newTo);
                            List<SolutionSeedRoute> routes = binding.routes().stream()
                                    .map(route -> route.routeId().equals(from.routeId()) ? solutionRoute(newFromRoute)
                                            : route.routeId().equals(to.routeId()) ? solutionRoute(newToRoute)
                                            : solutionRoute(route))
                                    .toList();
                            double coverage = binding.orderById().isEmpty() ? seed.coverageRate() : coveredOrders(routes) / (double) binding.orderById().size();
                            double score = objective(Math.round(coverage * Math.max(1, binding.orderById().size())), Math.max(1, binding.orderById().size()), round(newKm), newLate);
                            SolutionSeedCandidate candidate = new SolutionSeedCandidate(
                                    seed.solutionSeedId() + "-VROOM-SPLIT",
                                    CandidateSource.VROOM_SEED_IMPROVED,
                                    routes,
                                    coverage,
                                    round(newKm),
                                    newLate,
                                    routes.stream().map(route -> new DriverSeedLoad(route.driverId(), route.orderIds().size())).toList(),
                                    seed.hardFeasible(),
                                    seed.hardInvalidReason(),
                                    seed.softPenaltyReasons(),
                                    new HybridCostBreakdown(round(newKm), newLate * 10.0, 0.0, 0.0, 0.0, 0.0, score));
                            if (LexicographicSolutionComparator.SLA_STRICT.compare(candidate, best) > 0) {
                                best = candidate;
                                double oldPairKm = oldFrom.totalKm() + oldTo.totalKm();
                                double newPairKm = newFrom.totalKm() + newTo.totalKm();
                                bestReason = "vroom-split-accepted:" + orderId + ":" + from.routeId() + "->" + to.routeId() + ":-" + round(seed.totalDistanceKm() - candidate.totalDistanceKm()) + "km";
                                bestTrace = new MoveEvaluationTrace(
                                        "VROOM-SPLIT-" + orderId + "-" + from.routeId() + "-" + to.routeId(),
                                        from.routeId() + "->" + to.routeId(),
                                        "VROOM_SPLIT_RELOCATE",
                                        round(oldPairKm),
                                        round(newPairKm),
                                        round(oldPairKm - newPairKm),
                                        true,
                                        "accepted",
                                        List.of());
                            }
                        }
                    }
                }
            }
        }
        if (bestTrace == null) {
            bestTrace = new MoveEvaluationTrace("VROOM-SPLIT-NONE", "vroom", "VROOM_SPLIT_RELOCATE", seed.totalDistanceKm(), best.totalDistanceKm(), round(seed.totalDistanceKm() - best.totalDistanceKm()), false, "no-improving-feasible-split", List.of());
        }
        return new VroomIntensifierResult(best, bestTrace, bestReason);
    }

    private VroomIntensifierResult vroomSubsetSplitToEmptyDriver(SolutionSeedCandidate seed,
                                                                 SeedRouteBinding binding,
                                                                 SolutionSeedCandidate incumbent,
                                                                 DistanceCostFunction distanceCost,
                                                                 boolean seedRequiresLateZero) {
        SolutionSeedCandidate best = incumbent;
        MoveEvaluationTrace bestTrace = null;
        String bestReason = "vroom-subset-split-rejected:no-empty-driver-improvement";
        for (BoundRoute from : binding.routes()) {
            if (from.orderIds().size() < 2) {
                continue;
            }
            for (BoundRoute to : binding.routes()) {
                if (from.routeId().equals(to.routeId()) || !to.orderIds().isEmpty()) {
                    continue;
                }
                BoundStop toStart = to.stops().stream().filter(stop -> stop.type() == StopType.DRIVER_START).findFirst().orElse(null);
                if (toStart == null) {
                    continue;
                }
                for (int size = 2; size <= Math.min(4, from.orderIds().size()); size++) {
                    for (Set<String> movedOrders : orderSubsets(from.orderIds(), size)) {
                        List<BoundStop> movedStops = from.stops().stream()
                                .filter(stop -> stop.type() != StopType.DRIVER_START && movedOrders.contains(stop.orderId()))
                                .toList();
                        List<BoundStop> toPath = new ArrayList<>();
                        search(toStart, movedStops, new ArrayList<>(), new LinkedHashSet<>(), new LinkedHashSet<>(), 0.0, new double[]{Double.POSITIVE_INFINITY}, toPath, distanceCost);
                        if (toPath.isEmpty()) {
                            continue;
                        }
                        List<BoundStop> fromPath = from.stops().stream()
                                .filter(stop -> stop.type() != StopType.DRIVER_START && !movedOrders.contains(stop.orderId()))
                                .toList();
                        RouteSchedule oldFrom = scheduleEvaluator.evaluate(from, null, distanceCost, binding.orderById(), schedulePolicy, "vroom-subset-old-from");
                        RouteSchedule oldTo = scheduleEvaluator.evaluate(to, null, distanceCost, binding.orderById(), schedulePolicy, "vroom-subset-old-to");
                        RouteSchedule newFrom = scheduleEvaluator.evaluate(from, fromPath, distanceCost, binding.orderById(), schedulePolicy, "vroom-subset-new-from");
                        RouteSchedule newTo = scheduleEvaluator.evaluate(to, toPath, distanceCost, binding.orderById(), schedulePolicy, "vroom-subset-new-to");
                        long newLate = binding.routes().stream()
                                .filter(route -> !route.routeId().equals(from.routeId()) && !route.routeId().equals(to.routeId()))
                                .mapToLong(BoundRoute::lateOrderCount)
                                .sum() + newFrom.lateOrderCount() + newTo.lateOrderCount();
                        if (seedRequiresLateZero && newLate > 0) {
                            continue;
                        }
                        double newKm = binding.routes().stream()
                                .filter(route -> !route.routeId().equals(from.routeId()) && !route.routeId().equals(to.routeId()))
                                .mapToDouble(BoundRoute::distanceKm)
                                .sum() + newFrom.totalKm() + newTo.totalKm();
                        if (round(newKm) + 0.05 >= Math.min(best.totalDistanceKm(), seed.totalDistanceKm())) {
                            continue;
                        }
                        BoundRoute newFromRoute = routeFromSchedule(from, fromPath, newFrom);
                        BoundRoute newToRoute = routeFromSchedule(to, toPath, newTo);
                        List<SolutionSeedRoute> routes = binding.routes().stream()
                                .map(route -> route.routeId().equals(from.routeId()) ? solutionRoute(newFromRoute)
                                        : route.routeId().equals(to.routeId()) ? solutionRoute(newToRoute)
                                        : solutionRoute(route))
                                .toList();
                        double coverage = binding.orderById().isEmpty() ? seed.coverageRate() : coveredOrders(routes) / (double) binding.orderById().size();
                        double score = objective(Math.round(coverage * Math.max(1, binding.orderById().size())), Math.max(1, binding.orderById().size()), round(newKm), newLate);
                        SolutionSeedCandidate candidate = new SolutionSeedCandidate(
                                seed.solutionSeedId() + "-VROOM-SUBSET-SPLIT",
                                CandidateSource.VROOM_SEED_IMPROVED,
                                routes,
                                coverage,
                                round(newKm),
                                newLate,
                                routes.stream().map(route -> new DriverSeedLoad(route.driverId(), route.orderIds().size())).toList(),
                                seed.hardFeasible(),
                                seed.hardInvalidReason(),
                                seed.softPenaltyReasons(),
                                new HybridCostBreakdown(round(newKm), newLate * 10.0, 0.0, 0.0, 0.0, 0.0, score));
                        if (LexicographicSolutionComparator.SLA_STRICT.compare(candidate, best) > 0) {
                            best = candidate;
                            double oldPairKm = oldFrom.totalKm() + oldTo.totalKm();
                            double newPairKm = newFrom.totalKm() + newTo.totalKm();
                            bestReason = "vroom-subset-split-accepted:" + String.join("+", movedOrders) + ":" + from.routeId() + "->" + to.routeId() + ":-" + round(seed.totalDistanceKm() - candidate.totalDistanceKm()) + "km";
                            bestTrace = new MoveEvaluationTrace(
                                    "VROOM-SUBSET-SPLIT-" + String.join("-", movedOrders) + "-" + from.routeId() + "-" + to.routeId(),
                                    from.routeId() + "->" + to.routeId(),
                                    "VROOM_SUBSET_SPLIT",
                                    round(oldPairKm),
                                    round(newPairKm),
                                    round(oldPairKm - newPairKm),
                                    true,
                                    "accepted",
                                    List.of());
                        }
                    }
                }
            }
        }
        if (bestTrace == null) {
            bestTrace = new MoveEvaluationTrace("VROOM-SUBSET-SPLIT-NONE", "vroom", "VROOM_SUBSET_SPLIT", seed.totalDistanceKm(), best.totalDistanceKm(), round(seed.totalDistanceKm() - best.totalDistanceKm()), false, "no-empty-driver-improvement", List.of());
        }
        return new VroomIntensifierResult(best, bestTrace, bestReason);
    }

    private RouteAttempt permuteRoute(BoundRoute route, SeedRouteBinding binding, DistanceCostFunction distanceCost, boolean seedRequiresLateZero, AdaptiveMlPolicyConfig adaptiveConfig) {
        List<BoundStop> pickups = route.stops().stream().filter(stop -> stop.type() == StopType.PICKUP).toList();
        List<BoundStop> dropoffs = route.stops().stream().filter(stop -> stop.type() == StopType.DROPOFF).toList();
        if (pickups.isEmpty() || pickups.size() != dropoffs.size()) {
            return originalRoute(route, binding, distanceCost, "unsupported-route-size");
        }
        if (pickups.size() > maxExactReorderOrders(route, adaptiveConfig)) {
            return greedyRoute(route, binding, distanceCost, seedRequiresLateZero);
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

    private RouteAttempt greedyRoute(BoundRoute route, SeedRouteBinding binding, DistanceCostFunction distanceCost, boolean seedRequiresLateZero) {
        BoundStop start = route.stops().stream().filter(stop -> stop.type() == StopType.DRIVER_START).findFirst().orElse(null);
        if (start == null) {
            return originalRoute(route, binding, distanceCost, "missing-driver-start");
        }
        List<BoundStop> remaining = new ArrayList<>(route.stops().stream().filter(stop -> stop.type() != StopType.DRIVER_START).toList());
        List<BoundStop> path = new ArrayList<>();
        Set<String> pickedOrders = new LinkedHashSet<>();
        BoundStop current = start;
        while (!remaining.isEmpty()) {
            BoundStop from = current;
            BoundStop next = remaining.stream()
                    .filter(stop -> stop.type() == StopType.PICKUP || pickedOrders.contains(stop.orderId()))
                    .min(Comparator.comparingDouble(stop -> distanceCost.distanceKm("hybrid-greedy-" + from.stopId() + "-" + stop.stopId(), from.location().latitude(), from.location().longitude(), stop.location().latitude(), stop.location().longitude())))
                    .orElse(null);
            if (next == null) {
                return originalRoute(route, binding, distanceCost, "greedy-no-valid-next-stop");
            }
            path.add(next);
            remaining.remove(next);
            if (next.type() == StopType.PICKUP) {
                pickedOrders.add(next.orderId());
            }
            current = next;
        }
        RouteAttempt original = originalRoute(route, binding, distanceCost, "baseline-route");
        RouteAttempt attempt = routeAttempt(route, start, path, binding, distanceCost, "greedy-vroom-reorder-attempted");
        MoveEvaluationTrace trace = moveTrace(route, original, attempt, route.lateOrderCount(), seedRequiresLateZero);
        if (trace.accepted()) {
            return new RouteAttempt(true, attempt.orderIds(), attempt.stopSequence(), attempt.distanceKm(), attempt.durationMinutes(), attempt.lateOrders(), "greedy-vroom-reorder-improved", trace);
        }
        return withTrace(original, trace);
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

    private BoundRoute routeFromSchedule(BoundRoute original, List<BoundStop> path, RouteSchedule schedule) {
        List<String> orderIds = path.stream().filter(stop -> stop.type() == StopType.PICKUP).map(BoundStop::orderId).distinct().toList();
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

    private List<Set<String>> orderSubsets(List<String> orderIds, int size) {
        List<Set<String>> subsets = new ArrayList<>();
        collectOrderSubsets(orderIds, size, 0, new LinkedHashSet<>(), subsets);
        return subsets;
    }

    private void collectOrderSubsets(List<String> orderIds, int size, int index, Set<String> current, List<Set<String>> subsets) {
        if (current.size() == size) {
            subsets.add(new LinkedHashSet<>(current));
            return;
        }
        if (index >= orderIds.size() || subsets.size() >= 120) {
            return;
        }
        current.add(orderIds.get(index));
        collectOrderSubsets(orderIds, size, index + 1, current, subsets);
        current.remove(orderIds.get(index));
        collectOrderSubsets(orderIds, size, index + 1, current, subsets);
    }

    private double objective(long assignedOrders, long inputOrders, double distanceKm, long lateOrders) {
        long safeInput = Math.max(1, inputOrders);
        return (assignedOrders / (double) safeInput) * 1_000_000.0 - Math.max(0, inputOrders - assignedOrders) * 1_000_000.0 - distanceKm * 100.0 - lateOrders * 10_000.0;
    }

    private int maxExactReorderOrders(BoundRoute route, AdaptiveMlPolicyConfig adaptiveConfig) {
        if (adaptiveConfig != null && adaptiveConfig.qualitySeeking()) {
            return 6;
        }
        return route.routeId() != null && route.routeId().startsWith("VROOM-") ? 6 : 5;
    }

    private SolutionSeedCandidate withImprovedSource(SolutionSeedCandidate original, SolutionSeedCandidate selected) {
        if (selected == null || original == null || selected.source() == improvedSourceFor(original.source())) {
            return selected;
        }
        if (LexicographicSolutionComparator.SLA_STRICT.compare(selected, original) <= 0) {
            return selected;
        }
        CandidateSource improvedSource = improvedSourceFor(original.source());
        return new SolutionSeedCandidate(
                selected.solutionSeedId(),
                improvedSource,
                selected.routes(),
                selected.coverageRate(),
                selected.totalDistanceKm(),
                selected.lateOrderCount(),
                selected.driverLoadSummary(),
                selected.hardFeasible(),
                selected.hardInvalidReason(),
                selected.softPenaltyReasons(),
                selected.costBreakdown());
    }

    private CandidateSource improvedSource(SolutionSeedCandidate original, SolutionSeedCandidate selected) {
        if (original != null && selected != null && LexicographicSolutionComparator.SLA_STRICT.compare(selected, original) > 0) {
            return improvedSourceFor(original.source());
        }
        return selected == null || selected.source() == null ? (original == null ? CandidateSource.IRX_NATIVE : original.source()) : selected.source();
    }

    private CandidateSource improvedSource(SolutionSeedCandidate original, MoveEvaluationResult move) {
        return original != null && move != null && move.accepted()
                ? improvedSourceFor(original.source())
                : original == null ? CandidateSource.IRX_NATIVE : original.source();
    }

    private CandidateSource improvedSourceFor(CandidateSource source) {
        if (source == CandidateSource.VROOM_SEED) {
            return CandidateSource.VROOM_SEED_IMPROVED;
        }
        if (source == CandidateSource.PYVRP_SEED) {
            return CandidateSource.PYVRP_SEED_IMPROVED;
        }
        if (source == CandidateSource.ORTOOLS_SEED) {
            return CandidateSource.ORTOOLS_SEED_IMPROVED;
        }
        if (source == CandidateSource.IRX_NATIVE) {
            return CandidateSource.IRX_NATIVE_IMPROVED;
        }
        return source == null ? CandidateSource.BEST_EXTERNAL_SEED_IMPROVED : source;
    }

    private SolutionSeedCandidate emptySeed(SeedRouteBinding binding) {
        return new SolutionSeedCandidate(binding.seedId(), binding.source(), List.of(), 0.0, 0.0, 0, List.of(), false, "missing-seed", List.of("missing-seed"), new HybridCostBreakdown(0, 0, 0, 0, 0, 0, -1_000_000));
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private record RouteAttempt(boolean accepted, List<String> orderIds, List<String> stopSequence, double distanceKm, double durationMinutes, long lateOrders, String reason, MoveEvaluationTrace moveTrace) {
    }

    private record VroomIntensifierResult(SolutionSeedCandidate candidate, MoveEvaluationTrace trace, String reason) {
    }
}


