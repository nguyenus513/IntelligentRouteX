package com.routechain.v2.bundle;

import com.routechain.v2.EtaContext;
import com.routechain.v2.active.ActiveRouteState;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class DriverBundleMatcher {
    private final AdaptiveMlBundleDispatchLayer adaptiveLayer;

    public DriverBundleMatcher() {
        this(new AdaptiveMlBundleDispatchLayer());
    }

    public DriverBundleMatcher(AdaptiveMlBundleDispatchLayer adaptiveLayer) {
        this.adaptiveLayer = adaptiveLayer;
    }

    public List<DriverBundleAssignment> match(List<ActiveRouteState> activeRoutes,
                                              List<BundleCandidate> bundles,
                                              BundleContext context,
                                              EtaContext etaContext,
                                              Instant decisionTime) {
        if (activeRoutes == null || activeRoutes.isEmpty() || bundles == null || bundles.isEmpty()) {
            return List.of();
        }
        List<DriverBundleAssignment> candidates = new ArrayList<>();
        for (ActiveRouteState route : activeRoutes) {
            for (BundleCandidate bundle : bundles) {
                candidates.add(score(route, bundle, context, etaContext, decisionTime));
            }
        }
        Set<String> usedDrivers = new HashSet<>();
        Set<String> usedOrders = new HashSet<>();
        List<DriverBundleAssignment> selected = new ArrayList<>();
        for (DriverBundleAssignment candidate : candidates.stream()
                .sorted((left, right) -> Double.compare(left.cost(), right.cost()))
                .toList()) {
            if (usedDrivers.contains(candidate.driverId())) {
                continue;
            }
            if (candidate.orderIds().stream().anyMatch(usedOrders::contains)) {
                continue;
            }
            selected.add(candidate);
            usedDrivers.add(candidate.driverId());
            usedOrders.addAll(candidate.orderIds());
        }
        return List.copyOf(selected);
    }

    private DriverBundleAssignment score(ActiveRouteState route,
                                         BundleCandidate bundle,
                                         BundleContext context,
                                         EtaContext etaContext,
                                         Instant decisionTime) {
        double insertCost = clamp((route.projectedCompletionEtaMinutes() / 60.0) + (bundle.orderIds().size() * 0.08));
        double latePenalty = adaptiveLayer.breakRisk(bundle, context, etaContext, decisionTime);
        double detourPenalty = clamp(1.0 - context.averagePairSupport(bundle.orderIds()));
        double churnPenalty = clamp(1.0 - route.routeStabilityScore());
        double driverFit = clamp(route.routeStabilityScore() * 0.55 + (1.0 - insertCost) * 0.45);
        double bundleScore = clamp(bundle.score());
        double cost = round(0.30 * insertCost
                + 0.25 * latePenalty
                + 0.20 * detourPenalty
                + 0.15 * churnPenalty
                - 0.10 * driverFit
                - 0.10 * bundleScore);
        return new DriverBundleAssignment(
                "driver-bundle-assignment/v1",
                route.driverId(),
                route.routeId(),
                bundle.bundleId(),
                bundle.orderIds(),
                cost,
                insertCost,
                latePenalty,
                detourPenalty,
                churnPenalty,
                driverFit,
                bundleScore,
                List.of("min-cost-driver-bundle-matching", "forecast-late-risk-cost", "routefinder-sequence-cost"));
    }

    private double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }

    private double round(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }
}
