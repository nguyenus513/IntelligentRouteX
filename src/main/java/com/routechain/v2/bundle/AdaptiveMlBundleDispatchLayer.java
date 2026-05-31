package com.routechain.v2.bundle;

import com.routechain.domain.Order;
import com.routechain.v2.EtaContext;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class AdaptiveMlBundleDispatchLayer {

    public double admissionPriority(Order order,
                                    BundleContext context,
                                    EtaContext etaContext,
                                    Instant decisionTime) {
        double ageScore = ageScore(order, decisionTime);
        double lateRisk = lateRisk(order, etaContext, decisionTime);
        double regretScore = regretScore(order, context);
        double nearbyDriverScore = nearbyDriverScore(order, etaContext);
        double bundlePotential = bundlePotential(order, context);
        return round(0.30 * ageScore
                + 0.25 * lateRisk
                + 0.20 * regretScore
                + 0.15 * nearbyDriverScore
                + 0.10 * bundlePotential);
    }

    public BundleCandidate scoreBundle(BundleCandidate candidate,
                                       BundleContext context,
                                       EtaContext etaContext,
                                       Instant decisionTime,
                                       double routeSequenceQuality) {
        List<Order> orders = context.orders(candidate.orderIds());
        double pickupCluster = clamp(context.averagePairSupport(candidate.orderIds()));
        double directionFit = directionFit(candidate, context);
        double deadlineFit = deadlineFit(orders);
        double distanceSaving = clamp((candidate.orderIds().size() - 1) / 3.0 * pickupCluster);
        double ageBalance = orders.stream()
                .mapToDouble(order -> ageScore(order, decisionTime))
                .average()
                .orElse(0.0);
        double detourPenalty = clamp(1.0 - pickupCluster);
        double latePenalty = orders.stream()
                .mapToDouble(order -> lateRisk(order, etaContext, decisionTime))
                .average()
                .orElse(0.0);
        double familyBoost = candidate.family() == BundleFamily.URGENT_COMPANION ? 0.08 : 0.0;
        double sourceBoost = candidate.proposalSource() == BundleProposalSource.GREEDRL_PROPOSAL ? 0.25 : 0.0;
        double adaptiveScore = familyBoost + sourceBoost
                + 0.20 * pickupCluster
                + 0.20 * directionFit
                + 0.20 * deadlineFit
                + 0.15 * distanceSaving
                + 0.15 * clamp(routeSequenceQuality)
                + 0.10 * ageBalance
                - 0.30 * detourPenalty
                - 0.40 * latePenalty;
        return copyWithScore(candidate, round(adaptiveScore));
    }

    public List<BundleCandidate> greedySetPack(List<BundleCandidate> candidates) {
        List<BundleCandidate> selected = new ArrayList<>();
        Set<String> usedOrderIds = new HashSet<>();
        for (BundleCandidate candidate : candidates.stream()
                .sorted((left, right) -> Double.compare(right.score(), left.score()))
                .toList()) {
            if (candidate.orderIds().stream().noneMatch(usedOrderIds::contains)) {
                selected.add(candidate);
                usedOrderIds.addAll(candidate.orderIds());
            }
        }
        return List.copyOf(selected);
    }

    public double breakRisk(BundleCandidate candidate,
                            BundleContext context,
                            EtaContext etaContext,
                            Instant decisionTime) {
        List<Order> orders = context.orders(candidate.orderIds());
        double lateRisk = orders.stream()
                .mapToDouble(order -> lateRisk(order, etaContext, decisionTime))
                .average()
                .orElse(0.0);
        double detourRisk = clamp(1.0 - context.averagePairSupport(candidate.orderIds()));
        double oldOrderRisk = orders.stream()
                .mapToDouble(order -> ageScore(order, decisionTime))
                .max()
                .orElse(0.0);
        double overloadRisk = clamp((candidate.orderIds().size() - 3) / 2.0);
        double churnRisk = candidate.boundaryCross() ? 0.65 : 0.20;
        return round(0.35 * lateRisk
                + 0.25 * detourRisk
                + 0.15 * oldOrderRisk
                + 0.15 * overloadRisk
                + 0.10 * churnRisk);
    }

    public Map<String, Object> feedbackSummary(List<BundleCandidate> selectedBundles,
                                               BundleContext context,
                                               EtaContext etaContext,
                                               Instant decisionTime) {
        return Map.of(
                "layer", "Adaptive ML-Bundle Dispatch Layer",
                "forecastUsage", "lateRisk/breakRisk",
                "routeFinderUsage", "routeSequenceQuality/bundleSequenceScore",
                "greedRlUsage", "destroyRepairOperatorPolicy",
                "selectedBundleCount", selectedBundles.size(),
                "maxBreakRisk", selectedBundles.stream()
                        .mapToDouble(candidate -> breakRisk(candidate, context, etaContext, decisionTime))
                        .max()
                        .orElse(0.0));
    }

    private double ageScore(Order order, Instant decisionTime) {
        long waitingSeconds = Math.max(0L, Duration.between(order.readyAt(), decisionTime).toSeconds());
        double promisedSeconds = Math.max(60.0, order.promisedEtaMinutes() * 60.0);
        return clamp(waitingSeconds / promisedSeconds);
    }

    private double lateRisk(Order order, EtaContext etaContext, Instant decisionTime) {
        double agePressure = ageScore(order, decisionTime) * 0.55;
        double etaPressure = clamp(etaContext.averageEtaMinutes() / Math.max(1.0, order.promisedEtaMinutes())) * 0.20;
        double uncertaintyPressure = clamp(etaContext.averageUncertainty()) * 0.10;
        double badSignalPressure = (etaContext.trafficBadSignal() || etaContext.weatherBadSignal()) ? 0.10 : 0.0;
        double urgencyPressure = order.urgent() ? 0.15 : 0.0;
        return clamp(0.10 + agePressure + etaPressure + uncertaintyPressure + badSignalPressure + urgencyPressure);
    }

    private double regretScore(Order order, BundleContext context) {
        List<Double> supports = context.allOrders().stream()
                .filter(candidate -> !candidate.orderId().equals(order.orderId()))
                .map(candidate -> context.support(order.orderId(), candidate.orderId()))
                .filter(support -> support > 0.0)
                .sorted((left, right) -> Double.compare(right, left))
                .toList();
        if (supports.isEmpty()) {
            return 0.75;
        }
        if (supports.size() == 1) {
            return clamp(1.0 - supports.getFirst());
        }
        double bestInsertCost = 1.0 - supports.get(0);
        double secondBestInsertCost = 1.0 - supports.get(1);
        return clamp(secondBestInsertCost - bestInsertCost);
    }

    private double nearbyDriverScore(Order order, EtaContext etaContext) {
        double etaFit = 1.0 - clamp(etaContext.averageEtaMinutes() / Math.max(1.0, order.promisedEtaMinutes()));
        return clamp(etaFit + (order.urgent() ? 0.10 : 0.0));
    }

    private double bundlePotential(Order order, BundleContext context) {
        return context.allOrders().stream()
                .map(Order::orderId)
                .filter(candidateId -> !candidateId.equals(order.orderId()))
                .mapToDouble(candidateId -> context.support(order.orderId(), candidateId))
                .max()
                .orElse(0.0);
    }

    private double directionFit(BundleCandidate candidate, BundleContext context) {
        double support = context.averagePairSupport(candidate.orderIds());
        double familyLift = candidate.family() == BundleFamily.CORRIDOR_CHAIN ? 0.10 : 0.0;
        return clamp(support + familyLift);
    }

    private double deadlineFit(List<Order> orders) {
        if (orders.size() <= 1) {
            return 1.0;
        }
        long minReady = orders.stream().mapToLong(order -> order.readyAt().getEpochSecond()).min().orElse(0L);
        long maxReady = orders.stream().mapToLong(order -> order.readyAt().getEpochSecond()).max().orElse(minReady);
        double spreadMinutes = Math.max(0.0, (maxReady - minReady) / 60.0);
        double promisedAverage = orders.stream().mapToInt(Order::promisedEtaMinutes).average().orElse(20.0);
        return clamp(1.0 - spreadMinutes / Math.max(1.0, promisedAverage));
    }

    private BundleCandidate copyWithScore(BundleCandidate candidate, double score) {
        return new BundleCandidate(
                candidate.schemaVersion(),
                candidate.bundleId(),
                candidate.proposalSource(),
                candidate.family(),
                candidate.clusterId(),
                candidate.boundaryCross(),
                candidate.acceptedBoundaryOrderIds(),
                candidate.orderIds(),
                candidate.orderSetSignature(),
                candidate.seedOrderId(),
                candidate.corridorSignature(),
                score,
                candidate.feasible(),
                candidate.degradeReasons());
    }

    private double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }

    private double round(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }
}
