package com.routechain.v2.active;

import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.v2.cluster.EtaLegCache;
import com.routechain.v2.context.EtaEstimate;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class ActiveRouteInsertionGenerator {
    private static final int MAX_ACTIVE_STOPS = 6;
    private static final double MAX_COMPLETION_DELTA_MINUTES = 12.0;
    private static final double MAX_FRESHNESS_RISK = 0.85;
    private static final double MAX_CHURN_RISK = 0.50;
    private final ActiveRouteSequenceRepairer sequenceRepairer = new ActiveRouteSequenceRepairer();
    private final ActiveRouteLnsOptimizer lnsOptimizer = new ActiveRouteLnsOptimizer();

    public List<ActiveRouteInsertionCandidate> generate(List<ActiveRouteState> activeRoutes,
                                                        List<Order> candidateOrders,
                                                        Instant decisionTime,
                                                        EtaLegCache etaLegCache) {
        if (activeRoutes == null || activeRoutes.isEmpty() || candidateOrders == null || candidateOrders.isEmpty()) {
            return List.of();
        }
        Map<String, Order> orderById = candidateOrders.stream()
                .collect(Collectors.toMap(Order::orderId, Function.identity(), (left, right) -> left));
        List<ActiveRouteInsertionCandidate> candidates = new ArrayList<>();
        for (ActiveRouteState route : activeRoutes) {
            if (route.remainingStopOrder().size() > MAX_ACTIVE_STOPS) {
                continue;
            }
            for (Order order : candidateOrders) {
                if (route.assignedOrderIds().contains(order.orderId())) {
                    continue;
                }
                candidates.addAll(generateForRoute(route, order, orderById, decisionTime, etaLegCache));
            }
        }
        List<ActiveRouteInsertionCandidate> ranked = candidates.stream()
                .map(candidate -> withRegretReason(candidate, candidates))
                .sorted(Comparator.comparing(ActiveRouteInsertionCandidate::feasible).reversed()
                        .thenComparing(Comparator.comparingDouble(ActiveRouteInsertionCandidate::score).reversed())
                        .thenComparingDouble(ActiveRouteInsertionCandidate::projectedCompletionEtaMinutes)
                        .thenComparing(ActiveRouteInsertionCandidate::candidateId))
                .toList();
        ActiveRouteLnsRepairResult repairResult = lnsOptimizer.improve(ranked);
        return repairResult.candidates().isEmpty() ? ranked : repairResult.candidates();
    }

    private List<ActiveRouteInsertionCandidate> generateForRoute(ActiveRouteState route,
                                                                 Order order,
                                                                 Map<String, Order> orderById,
                                                                 Instant decisionTime,
                                                                 EtaLegCache etaLegCache) {
        List<ActiveRouteInsertionCandidate> candidates = new ArrayList<>();
        List<ActiveRouteStop> baseStops = baseStopSequence(route, orderById);
        int insertionLimit = Math.min(baseStops.size(), MAX_ACTIVE_STOPS * 2);
        for (int pickupIndex = 0; pickupIndex <= insertionLimit; pickupIndex++) {
            for (int dropoffIndex = pickupIndex + 1; dropoffIndex <= insertionLimit + 1; dropoffIndex++) {
                List<ActiveRouteStop> stopSequence = insertPickupDropoff(baseStops, order, pickupIndex, dropoffIndex);
                ActiveRouteSequenceRepairResult repairResult = sequenceRepairer.repair(route.currentLocation(), stopSequence);
                candidates.add(project(route, order, repairResult, pickupIndex, dropoffIndex, decisionTime, etaLegCache));
            }
        }
        return candidates.stream()
                .sorted(Comparator.comparing(ActiveRouteInsertionCandidate::feasible).reversed()
                        .thenComparing(Comparator.comparingDouble(ActiveRouteInsertionCandidate::score).reversed())
                        .thenComparingDouble(ActiveRouteInsertionCandidate::projectedCompletionEtaMinutes)
                        .thenComparing(ActiveRouteInsertionCandidate::candidateId))
                .limit(12)
                .toList();
    }

    private ActiveRouteInsertionCandidate withRegretReason(ActiveRouteInsertionCandidate candidate,
                                                           List<ActiveRouteInsertionCandidate> routeCandidates) {
        List<Double> feasibleScores = routeCandidates.stream()
                .filter(ActiveRouteInsertionCandidate::feasible)
                .map(ActiveRouteInsertionCandidate::score)
                .sorted(Comparator.reverseOrder())
                .toList();
        if (feasibleScores.size() < 2) {
            return candidate;
        }
        double regret2 = feasibleScores.get(0) - feasibleScores.get(1);
        if (candidate.score() < feasibleScores.get(0) || regret2 < 0.04) {
            return candidate;
        }
        List<String> reasons = new ArrayList<>(candidate.reasons());
        reasons.add("active-route-regret-2-stable-choice");
        return new ActiveRouteInsertionCandidate(
                candidate.schemaVersion(),
                candidate.candidateId(),
                candidate.routeId(),
                candidate.driverId(),
                candidate.insertedOrderId(),
                candidate.pickupInsertionIndex(),
                candidate.newStopOrder(),
                candidate.projectedPickupEtaMinutes(),
                candidate.projectedCompletionEtaMinutes(),
                candidate.incrementalCompletionEtaMinutes(),
                candidate.freshnessRisk(),
                candidate.churnRisk(),
                candidate.routeShapeRisk(),
                Math.min(1.0, candidate.score() + Math.min(0.05, regret2)),
                candidate.feasible(),
                reasons.stream().distinct().toList(),
                candidate.degradeReasons());
    }

    private ActiveRouteInsertionCandidate project(ActiveRouteState route,
                                                  Order insertedOrder,
                                                  ActiveRouteSequenceRepairResult repairResult,
                                                  int pickupInsertionIndex,
                                                  int dropoffInsertionIndex,
                                                  Instant decisionTime,
                                                  EtaLegCache etaLegCache) {
        List<ActiveRouteStop> stopSequence = repairResult.stopSequence();
        Projection projection = projectStopSequence(route.currentLocation(), stopSequence, insertedOrder.orderId(), etaLegCache);
        double completionDelta = Math.max(0.0, projection.completionEtaMinutes() - route.projectedCompletionEtaMinutes());
        double promiseSlackMinutes = Duration.between(decisionTime, insertedOrder.createdAt().plusSeconds(insertedOrder.promisedEtaMinutes() * 60L)).toSeconds() / 60.0;
        double freshnessRisk = risk(completionDelta, Math.max(1.0, promiseSlackMinutes));
        double churnRisk = churnRisk(pickupInsertionIndex, route.remainingStopOrder().size(), route.routeStabilityScore());
        double routeShapeRisk = routeShapeRisk(stopSequence, projection.completionEtaMinutes());
        List<String> degradeReasons = new ArrayList<>(projection.degradeReasons());
        boolean feasible = true;
        if (projection.pickupEtaMinutes() < readyDelayMinutes(decisionTime, insertedOrder)) {
            feasible = false;
            degradeReasons.add("active-insertion-pickup-before-ready");
        }
        if (completionDelta > MAX_COMPLETION_DELTA_MINUTES) {
            feasible = false;
            degradeReasons.add("active-insertion-completion-delta-too-high");
        }
        if (freshnessRisk > MAX_FRESHNESS_RISK) {
            feasible = false;
            degradeReasons.add("active-insertion-freshness-risk-too-high");
        }
        if (churnRisk > MAX_CHURN_RISK) {
            feasible = false;
            degradeReasons.add("active-insertion-churn-risk-too-high");
        }
        if (!projection.precedenceFeasible()) {
            feasible = false;
            degradeReasons.add("active-insertion-precedence-violation");
        }
        double score = score(completionDelta, freshnessRisk, churnRisk, routeShapeRisk, projection.pickupEtaMinutes(), feasible, repairResult.distanceDelta());
        List<String> reasons = new ArrayList<>(List.of("active-route-regret-insertion", "active-route-pickup-dropoff-precedence", "rolling-horizon-reoptimization-candidate"));
        reasons.addAll(repairResult.reasons());
        return new ActiveRouteInsertionCandidate(
                "active-route-insertion-candidate/v1",
                route.routeId() + ":insert:" + insertedOrder.orderId() + ":" + pickupInsertionIndex + ":" + dropoffInsertionIndex,
                route.routeId(),
                route.driverId(),
                insertedOrder.orderId(),
                pickupInsertionIndex,
                stopOrder(stopSequence),
                projection.pickupEtaMinutes(),
                projection.completionEtaMinutes(),
                completionDelta,
                freshnessRisk,
                churnRisk,
                routeShapeRisk,
                score,
                feasible,
                reasons.stream().distinct().toList(),
                degradeReasons.stream().distinct().toList());
    }

    private Projection projectStopSequence(GeoPoint currentLocation,
                                            List<ActiveRouteStop> stopSequence,
                                            String insertedOrderId,
                                            EtaLegCache etaLegCache) {
        double totalMinutes = 0.0;
        double insertedPickupEta = 0.0;
        List<String> degradeReasons = new ArrayList<>();
        GeoPoint currentPoint = currentLocation;
        Set<String> pickedUpOrderIds = new java.util.HashSet<>();
        boolean precedenceFeasible = true;
        for (ActiveRouteStop stop : stopSequence) {
            EtaEstimate eta = etaLegCache.getOrEstimate(
                    currentPoint,
                    stop.location(),
                    "active-route-insertion-sequence",
                    "active->" + stop.signature());
            totalMinutes += eta.etaMinutes();
            degradeReasons.addAll(eta.degradeReasons());
            if (stop.stopType() == ActiveRouteStopType.PICKUP) {
                pickedUpOrderIds.add(stop.orderId());
            } else if (!pickedUpOrderIds.contains(stop.orderId())) {
                precedenceFeasible = false;
            }
            if (stop.orderId().equals(insertedOrderId) && stop.stopType() == ActiveRouteStopType.PICKUP) {
                insertedPickupEta = totalMinutes;
            }
            currentPoint = stop.location();
        }
        return new Projection(insertedPickupEta, totalMinutes, precedenceFeasible, degradeReasons.stream().distinct().toList());
    }

    private List<ActiveRouteStop> baseStopSequence(ActiveRouteState route, Map<String, Order> orderById) {
        List<ActiveRouteStop> stops = new ArrayList<>();
        for (String orderId : route.remainingStopOrder()) {
            Order order = orderById.get(orderId);
            if (order != null) {
                stops.add(ActiveRouteStop.pickup(order));
            }
        }
        for (String orderId : route.remainingStopOrder()) {
            Order order = orderById.get(orderId);
            if (order != null) {
                stops.add(ActiveRouteStop.dropoff(order));
            }
        }
        return List.copyOf(stops);
    }

    private List<ActiveRouteStop> insertPickupDropoff(List<ActiveRouteStop> baseStops,
                                                      Order order,
                                                      int pickupIndex,
                                                      int dropoffIndex) {
        List<ActiveRouteStop> inserted = new ArrayList<>(baseStops);
        inserted.add(Math.max(0, Math.min(pickupIndex, inserted.size())), ActiveRouteStop.pickup(order));
        inserted.add(Math.max(0, Math.min(dropoffIndex, inserted.size())), ActiveRouteStop.dropoff(order));
        return List.copyOf(inserted);
    }

    private List<String> stopOrder(List<ActiveRouteStop> stopSequence) {
        return stopSequence.stream()
                .filter(stop -> stop.stopType() == ActiveRouteStopType.PICKUP)
                .map(ActiveRouteStop::orderId)
                .distinct()
                .toList();
    }

    private double readyDelayMinutes(Instant decisionTime, Order order) {
        return Math.max(0.0, Duration.between(decisionTime, order.readyAt()).toSeconds() / 60.0);
    }

    private double risk(double numerator, double denominator) {
        return Math.max(0.0, Math.min(1.0, numerator / denominator));
    }

    private double churnRisk(int insertionIndex, int activeStopCount, double stabilityScore) {
        if (activeStopCount <= 0) {
            return 0.0;
        }
        double frontInsertionRisk = 1.0 - ((double) insertionIndex / Math.max(1, activeStopCount));
        double stabilityRisk = 1.0 - Math.max(0.0, Math.min(1.0, stabilityScore));
        return Math.max(0.0, Math.min(1.0, 0.65 * frontInsertionRisk + 0.35 * stabilityRisk));
    }

    private double routeShapeRisk(List<ActiveRouteStop> stopSequence, double completionEtaMinutes) {
        long transitionCount = Math.max(1, stopSequence.size());
        double averageLegMinutes = completionEtaMinutes / transitionCount;
        double stopCountRisk = risk(Math.max(0, stopSequence.size() - 4), 8.0);
        return Math.max(0.0, Math.min(1.0, 0.55 * risk(averageLegMinutes, 10.0) + 0.45 * stopCountRisk));
    }

    private double score(double completionDelta,
                         double freshnessRisk,
                         double churnRisk,
                         double routeShapeRisk,
                         double pickupEtaMinutes,
                         boolean feasible,
                         double repairDelta) {
        double score = 1.0
                - 0.26 * risk(completionDelta, MAX_COMPLETION_DELTA_MINUTES)
                - 0.24 * freshnessRisk
                - 0.20 * churnRisk
                - 0.18 * routeShapeRisk
                - 0.12 * risk(pickupEtaMinutes, 18.0)
                + Math.min(0.04, Math.max(0.0, repairDelta * 20.0));
        if (!feasible) {
            score -= 0.50;
        }
        return Math.max(0.0, Math.min(1.0, score));
    }

    private record Projection(
            double pickupEtaMinutes,
            double completionEtaMinutes,
            boolean precedenceFeasible,
            List<String> degradeReasons) {
    }
}
